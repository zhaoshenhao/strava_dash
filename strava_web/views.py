# strava_web/views.py
import requests
import json
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.contrib.auth import login, authenticate, get_user_model
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.contrib.auth.models import Group
from django.contrib.auth.views import LogoutView
from .forms import StravaUserRegistrationForm, CustomUserProfileForm, ActivityEditForm 
from .models import GroupApplication, Activity
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _

User = get_user_model()

@require_http_methods(["GET"])
def strava_login(request):
    """
    引导用户到 Strava 进行授权。
    """
    client_id = settings.STRAVA_CLIENT_ID
    redirect_uri = request.build_absolute_uri(reverse('strava_callback'))
    scope = 'activity:read_all,profile:read_all' # 请求活动和个人资料权限

    # 实际应用中 state 参数需要生成并存储在 session 中，用于防止 CSRF 攻击
    state = 'secure_random_string' # 简化，请替换为安全机制
    request.session['strava_oauth_state'] = state 

    auth_url = (
        f"{settings.STRAVA_AUTHORIZE_URL}?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"scope={scope}&"
        f"approval_prompt=force&" # 强制用户重新授权以获取新的 refresh_token
        f"state={state}" 
    )
    return redirect(auth_url)

@require_http_methods(["GET"])
@transaction.atomic # 确保整个回调过程的原子性
def strava_callback(request):
    """
    处理 Strava 的 OAuth 回调，交换令牌并登录/注册用户。
    """
    code = request.GET.get('code')
    error = request.GET.get('error')
    state = request.GET.get('state')

    # 验证 CSRF state
    if state != request.session.get('strava_oauth_state'):
        messages.error(request, _("CSRF validation failed"))
        return HttpResponseRedirect(reverse('login'))
    del request.session['strava_oauth_state'] # 使用后删除

    if error:
        messages.error(request, _("Strava authorization failed: %(error)s") % {'error': error})
        return HttpResponseRedirect(reverse('login'))

    if not code:
        messages.error(request, _("Strava Auth code not received."))
        return HttpResponseRedirect(reverse('login'))

    client_id = settings.STRAVA_CLIENT_ID
    client_secret = settings.STRAVA_CLIENT_SECRET
    redirect_uri = request.build_absolute_uri(reverse('strava_callback'))

    token_payload = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': redirect_uri
    }

    try:
        response = requests.post(settings.STRAVA_TOKEN_URL, data=token_payload)
        response.raise_for_status() # 检查 HTTP 错误
        token_data = response.json()

        strava_athlete_id = token_data['athlete']['id']
        access_token = token_data['access_token']
        refresh_token = token_data['refresh_token']
        expires_in = token_data['expires_in'] # 过期秒数
        token_expires_at = timezone.now() + timedelta(seconds=expires_in)

        # 获取更详细的 Strava 用户信息
        athlete_info_response = requests.get(
            f"{settings.STRAVA_API_BASE_URL}/athlete",
            headers={'Authorization': f'Bearer {access_token}'}
        )
        athlete_info_response.raise_for_status()
        athlete_info = athlete_info_response.json()

        user, created = User.objects.get_or_create(
            strava_id=strava_athlete_id,
            defaults={
                'username': f"strava_{strava_athlete_id}", # 默认用户名，后续用户可修改
                'first_name': athlete_info.get('firstname', ''),
                'last_name': athlete_info.get('lastname', ''),
                'strava_access_token': access_token,
                'strava_refresh_token': refresh_token,
                'strava_token_expires_at': token_expires_at,
                'is_active': True,
            }
        )

        if not created:
            # 如果用户已存在，更新其 Strava 令牌
            user.strava_access_token = access_token
            user.strava_refresh_token = refresh_token
            user.strava_token_expires_at = token_expires_at
            user.save()

        # 对于通过 SSO 注册/登录的用户，设置密码为不可用 (如果他们没有手动设置过)
        if not user.has_usable_password():
            user.set_unusable_password() 
            user.save()

        # 登录用户
        authenticated_user = authenticate(request, strava_id=strava_athlete_id)
        if authenticated_user:
            login(request, authenticated_user)
            if created:
                messages.success(request, f"Welcome to Strava Dash，{user.get_full_name() or user.username}！Please complete your registration.")
                messages.success(request, _("Welcome to Strava Dash, %(username)s! Please complete your registration.") % {'username': user.get_full_name() or user.username})
                return HttpResponseRedirect(reverse('register')) # 新用户跳转到完善信息页
            else:
                messages.success(request, _("Welcome back, %(username)s!") % {'username': user.get_full_name() or user.username})
                return HttpResponseRedirect(reverse('personal_dashboard')) # 登录成功重定向
        else:
            messages.error(request, _("Strava login failed, please try again."))
            return HttpResponseRedirect(reverse('login'))

    except requests.exceptions.RequestException as e:
        messages.error(request, _("Connection to Strava failed: %(error_message)s") % {'error_message': e})
        return HttpResponseRedirect(reverse('login'))
    except json.JSONDecodeError:
        messages.error(request, _("Strava data format error."))
        return HttpResponseRedirect(reverse('login'))
    except Exception as e:
        messages.error(request, _("Unknown error: %(error_message)s") % {'error_message': e})
        return HttpResponseRedirect(reverse('login'))

@login_required
def register_user(request):
    """
    新用户 Strava SSO 注册后，完善邮件和密码信息。
    """
    if request.user.has_usable_password() and request.user.email:
        messages.info(request, _("Registration completed."))
        return redirect('personal_dashboard')

    if request.method == 'POST':
        form = StravaUserRegistrationForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)
            password = form.cleaned_data.get('password')
            if password: # 只有当用户提供了密码时才设置
                user.set_password(password)
            user.is_active = True # 确保账户激活
            user.save()
            messages.success(request, _("Registration completed."))
            # 重新登录以更新 session 中的用户认证状态
            login(request, user, backend='django.contrib.auth.backends.ModelBackend') 
            return redirect('personal_dashboard')
        else:
            messages.error(request, _("Please correct the error in the form."))
    else:
        form = StravaUserRegistrationForm(instance=request.user) # 预填充 Strava 提供的名字等

    context = {'form': form}
    return render(request, 'strava_web/register.html', context)


@login_required
def personal_dashboard(request):
    """
    显示个人 Dashboard，包含个人信息和加入的组。
    """
    print(f"Current language code in view: {request.LANGUAGE_CODE}")
    # 可以从 request.user 获取个人信息
    user_groups = request.user.groups.all()
    context = {
        'user': request.user,
        'user_groups': user_groups,
    }
    return render(request, 'strava_web/personal_dashboard.html', context)

@login_required
def profile_edit(request):
    """
    用户个人信息修改页面（不包括密码和组）。
    """
    if request.method == 'POST':
        form = CustomUserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("You profile has been updated."))
            return redirect('personal_dashboard')
        else:
            messages.error(request, _("Please correct the error in the form."))
    else:
        form = CustomUserProfileForm(instance=request.user)

    context = {'form': form}
    return render(request, 'strava_web/profile_edit.html', context)

@login_required
def group_membership_edit(request):
    """
    用户可以查看所有开放和封闭的组，并进行加入/申请/退出操作。
    增加按组群类型和是否是成员的搜索。
    """
    # 获取所有有 Dashboard 的组，排除 'admin' 组
    all_groups_queryset = Group.objects.filter(has_dashboard=True).exclude(name='admin') \
                                       .annotate(member_count=Count('member')) # 计算成员数

    # 搜索功能
    search_query = request.GET.get('search', '')
    if search_query:
        all_groups_queryset = all_groups_queryset.filter(
            Q(name__icontains=search_query) |
            Q(admin__username__icontains=search_query) |
            Q(admin__first_name__icontains=search_query) |
            Q(admin__last_name__icontains=search_query)
        )

    # 1. 按组群类型过滤
    group_type_filter = request.GET.get('group_type_filter', '')
    if group_type_filter:
        if group_type_filter == 'open':
            all_groups_queryset = all_groups_queryset.filter(is_open=True)
        elif group_type_filter == 'closed':
            all_groups_queryset = all_groups_queryset.filter(is_open=False)

    # 准备数据以包含群组类型、成员状态和申请状态（在过滤之前，因为is_member是针对当前用户）
    groups_data = []
    for group in all_groups_queryset:
        is_member = request.user.groups.filter(id=group.id).exists()
        application = None
        application_status_display = "" # 用于封闭组的申请状态
        action_button_text = ""
        action_button_class = ""
        action_button_disabled = False
        action_url_name = ""
        is_application_form = False # 判断是否是申请的表单

        if is_member:
            # 如果是成员，显示“退出”按钮
            action_button_text = _("Leave")
            action_button_class = "btn-danger"
            action_url_name = "leave_group" # 这是一个新的/修改后的URL，需要JS确认
        elif group.is_open:
            # 如果是开放组且不是成员，显示“加入”按钮
            action_button_text = _("Join")
            action_button_class = "btn-success"
            action_url_name = "join_group"
        else:
            # 如果是封闭组且不是成员，处理申请逻辑
            try:
                application = GroupApplication.objects.get(user=request.user, group=group)
                if application.status == 'pending':
                    application_status_display = _("Pending Approval")
                    action_button_text = _("Pending")
                    action_button_class = "btn-warning"
                    action_button_disabled = True
                elif application.status == 'rejected':
                    # 检查是否在拒绝后7天内
                    if application.reviewed_at and (timezone.now() - application.reviewed_at).days < 7:
                        application_status_display = _("Rejected (can re-apply after 7 days)")
                        action_button_text = _("Reject")
                        action_button_class = "btn-secondary"
                        action_button_disabled = True
                    else:
                        application_status_display = _("Rejected (Can reapply)")
                        action_button_text = _("Join") # 超过7天可重新申请
                        action_button_class = "btn-primary"
                        is_application_form = True # 标记为申请表单
                        action_url_name = "apply_for_group"
            except GroupApplication.DoesNotExist:
                # 未申请
                application_status_display = _("Not applied for")
                action_button_text = _("Join")
                action_button_class = "btn-primary"
                is_application_form = True # 标记为申请表单
                action_url_name = "apply_for_group"

        groups_data.append({
            'group': group,
            'group_type': _("Open") if group.is_open else _("Closed"),
            'is_member': is_member,
            'member_count': group.member_count,
            'application_status_display': application_status_display,
            'action_button_text': action_button_text,
            'action_button_class': action_button_class,
            'action_button_disabled': action_button_disabled,
            'action_url_name': action_url_name,
            'is_application_form': is_application_form,
        })
    
    # 2. 按是否是成员过滤
    is_member_filter = request.GET.get('is_member_filter', '')
    if is_member_filter:
        if is_member_filter == 'yes':
            groups_data = [item for item in groups_data if item['is_member']]
        elif is_member_filter == 'no':
            groups_data = [item for item in groups_data if not item['is_member']]
    sort_by = request.GET.get('sort_by', 'is_member') # 默认按是否是成员排序
    order = request.GET.get('order', 'asc') # 默认升序

    def get_sort_key(item):
        if sort_by == 'name':
            return item['group'].name
        elif sort_by == 'member_count':
            return item['member_count']
        elif sort_by == 'admin':
            return item['group'].admin.username if item['group'].admin else ''
        elif sort_by == 'group_type':
            return (0 if item['group'].is_open else 1, item['group'].name)
        elif sort_by == 'is_member':
            return (0 if item['is_member'] else 1, item['group'].name)
        return item['group'].name # 默认

    groups_data.sort(key=get_sort_key, reverse=(order == 'desc'))

    # 分页
    page = request.GET.get('page', 1)
    paginator = Paginator(groups_data, 20) # 每页20个
    try:
        groups_paginated = paginator.page(page)
    except PageNotAnInteger:
        groups_paginated = paginator.page(1)
    except EmptyPage:
        groups_paginated = paginator.page(paginator.num_pages)

    context = {
        'groups_paginated': groups_paginated,
        'search_query': search_query,
        'group_type_filter': group_type_filter, # 传递新的过滤参数
        'is_member_filter': is_member_filter,   # 传递新的过滤参数
        'sort_by': sort_by,
        'order': order,
    }
    return render(request, 'strava_web/group_membership_edit.html', context)

# 组群 Dashboard 占位符
@login_required
def group_dashboard(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not group.has_dashboard:
        messages.error(request, "该组没有独立的 Dashboard。")
        return redirect('personal_dashboard')

    if not request.user.groups.filter(id=group.id).exists():
        messages.error(request, "您没有权限查看该组的 Dashboard。")
        return redirect('personal_dashboard')

    # 检查当前用户是否是该群组的管理员
    is_group_admin = (group.admin == request.user)
    
    context = {
        'group': group,
        'is_group_admin': is_group_admin, # 将管理员状态传递给模板
        # 这里将是组群排行数据，待实现
    }
    return render(request, 'strava_web/group_dashboard.html', context)

# 群组管理页面（仅管理员可见）
@staff_member_required
def group_manage_members(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # 检查当前用户是否是该群组的管理员
    if group.admin != request.user:
        messages.error(request, _("You do not have permission to manage this group."))
        return redirect('group_dashboard', group_id=group.id)

    # 获取所有群组成员
    group_members = group.members.all()

    # 获取待处理的申请
    pending_applications = GroupApplication.objects.filter(group=group, status='pending')

    context = {
        'group': group,
        'group_members': group_members,
        'pending_applications': pending_applications, # 传递待处理申请
        'is_group_admin': True,
    }
    return render(request, 'strava_web/group_manage_members.html', context)

# 新增：申请加入封闭组
@login_required
@require_http_methods(["POST"])
def apply_for_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if group.is_open:
        messages.error(request, _("This is an open group and no application is required to join."))
        return redirect('group_membership_edit')

    if request.user.groups.filter(id=group.id).exists():
        messages.info(request, _("You are already a member of this group."))
        return redirect('group_membership_edit')

    # 检查是否有待处理或被拒绝但未过期的申请
    existing_application = GroupApplication.objects.filter(user=request.user, group=group).first()
    if existing_application:
        if existing_application.status == 'pending':
            messages.info(request, _("You have submitted your application, please wait for the administrator to review it."))
        elif existing_application.status == 'rejected' and \
             existing_application.reviewed_at and (timezone.now() - existing_application.reviewed_at).days < 7:
            messages.warning(request, _("Your application was recently rejected, please try again in 7 days."))
        else: # 超过7天，可以重新申请
            existing_application.delete() # 删除旧的被拒绝申请以便创建新的
            GroupApplication.objects.create(user=request.user, group=group, status='pending')
            messages.success(request, _("Application to join %(group_name)s submitted, please wait for admin review.") % {'group_name': group.name})
            return redirect('group_membership_edit')
        return redirect('group_membership_edit')


    # 创建新的申请
    GroupApplication.objects.create(user=request.user, group=group, status='pending')
    messages.success(request, _("Application to join %(group_name)s submitted, please wait for admin review.") % {'group_name': group.name})
    return redirect('group_membership_edit')


# 新增：群组管理员审核申请
@staff_member_required
@require_http_methods(["POST"])
def review_group_application(request, application_id):
    application = get_object_or_404(GroupApplication, id=application_id)
    group = application.group

    # 检查当前用户是否是该群组的管理员
    if group.admin != request.user:
        messages.error(request, _("You do not have permission to review this request."))
        return redirect('group_dashboard', group_id=group.id)

    action = request.POST.get('action') # 'approve' 或 'reject'

    if application.status != 'pending':
        messages.warning(request, _("The application has been processed."))
        return redirect('group_manage_members', group_id=group.id)

    if action == 'approve':
        application.status = 'approved'
        application.reviewed_at = timezone.now()
        application.reviewer = request.user
        application.save()
        group.members.add(application.user) # 将用户添加到群组
        messages.success(request, _("Approved %(username)s to join %(group_name)s.") % {'username': application.user.username,'group_name': group.name})
    elif action == 'reject':
        application.status = 'rejected'
        application.reviewed_at = timezone.now()
        application.reviewer = request.user
        application.save()
        messages.info(request, _("Rejected %(username)s from joining %(group_name)s.") % {'username': application.user.username,'group_name': group.name})
    else:
        messages.error(request, _("Invalid operation."))

    return redirect('group_manage_members', group_id=group.id)

@login_required
def join_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if group.is_open and group.has_dashboard and group.name != 'admin':
        if not request.user.groups.filter(id=group.id).exists():
            request.user.groups.add(group)
            messages.success(request, _("You have joined the group: %(gname)s.") % {'gname': group.name})
        else:
            messages.info(request, _("You are already in this group:%(gname)s.") % {'gname': group.name})
    else:
        messages.error(request, _("Group %(gname)s is not open.") % {'gname': group.name})
    return redirect('group_membership_edit') # 或重定向到组列表页面

@login_required
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user.groups.filter(id=group.id).exists():
        request.user.groups.remove(group)
        messages.success(request, _("You have left the group: %(gname)s") % {'gname': group.name})
    else:
        messages.info(request, _("You do not belong to this group: %(gname)s") % {'gname': group.name})
    return redirect('group_membership_edit') # 或重定向到组列表页面

def home(request):
    return render(request, 'strava_web/home.html')

class CustomLogoutView(LogoutView):
    next_page = 'home' # 登出后重定向到名为 'home' 的 URL

@login_required
def activities(request): # 函数名已恢复为 `activities`
    """
    Displays a list of the current user's Strava activities with filtering,
    pagination, and sorting.
    """
    user_activities = Activity.objects.filter(user=request.user)

    # --- Filtering Logic ---
    # 1. Date Filters (Year, Month, Week)
    selected_year = request.GET.get('year')
    selected_month = request.GET.get('month')
    selected_week = request.GET.get('week')

    if selected_year:
        user_activities = user_activities.filter(start_date_local__year=selected_year)
    if selected_month:
        user_activities = user_activities.filter(start_date_local__month=selected_month)
    if selected_week:
        # Note: '__week' filter might vary slightly based on database,
        # ensure it works correctly with your chosen DB (e.g., SQLite, PostgreSQL, MySQL)
        # For cross-DB compatibility, sometimes filtering by date range is more robust
        user_activities = user_activities.filter(start_date_local__week=selected_week)

    # Generate available years, months, weeks for dropdowns
    available_years = Activity.objects.filter(user=request.user) \
                                   .values_list('start_date_local__year', flat=True) \
                                   .distinct().order_by('-start_date_local__year')
    # Generate list of (month_number, month_name) for dropdown
    # Using gettext to translate month names if i18n is active
    available_months = [
        ('1', _('January')), ('2', _('February')), ('3', _('March')), ('4', _('April')),
        ('5', _('May')), ('6', _('June')), ('7', _('July')), ('8', _('August')),
        ('9', _('September')), ('10', _('October')), ('11', _('November')), ('12', _('December')),
    ]
    available_weeks = list(range(1, 53)) # Weeks 1-52

    # 2. Distance Filters (using values in meters as per Activity model) - 已恢复为你原始代码的逻辑
    selected_distance = request.GET.get('distance')
    # Define distance thresholds in METERS
    DIST_5K = 5000 # 5 km
    DIST_10K = 10000 # 10 km
    DIST_15K = 15000 # 15 km
    DIST_20K = 20000 # 20 km
    DIST_25K = 25000 # 25 km
    DIST_30K = 30000 # 30 km
    DIST_35K = 35000 # 35 km
    DIST_40K = 40000 # 40 km
    DIST_45K = 45000 # 45 km
    DIST_50K = 50000 # 50 km
    DIST_100K = 100000 # 100 km

    if selected_distance:
        if selected_distance == '0-5k':
            user_activities = user_activities.filter(distance__gte=0, distance__lt=DIST_5K)
        elif selected_distance == '5-10k':
            user_activities = user_activities.filter(distance__gte=DIST_5K, distance__lt=DIST_10K)
        elif selected_distance == '10-15k':
            user_activities = user_activities.filter(distance__gte=DIST_10K, distance__lt=DIST_15K)
        elif selected_distance == '15-20k':
            user_activities = user_activities.filter(distance__gte=DIST_15K, distance__lt=DIST_20K)
        elif selected_distance == '20-25k':
            user_activities = user_activities.filter(distance__gte=DIST_20K, distance__lt=DIST_25K)
        elif selected_distance == '25-30k':
            user_activities = user_activities.filter(distance__gte=DIST_25K, distance__lt=DIST_30K)
        elif selected_distance == '30-35k':
            user_activities = user_activities.filter(distance__gte=DIST_30K, distance__lt=DIST_35K)
        elif selected_distance == '35-40k':
            user_activities = user_activities.filter(distance__gte=DIST_35K, distance__lt=DIST_40K)
        elif selected_distance == '40-45k':
            user_activities = user_activities.filter(distance__gte=DIST_40K, distance__lt=DIST_45K)
        elif selected_distance == '45-50k':
            user_activities = user_activities.filter(distance__gte=DIST_45K, distance__lt=DIST_50K)
        elif selected_distance == '50-100k':
            user_activities = user_activities.filter(distance__gte=DIST_50K, distance__lt=DIST_100K)
        elif selected_distance == '100k_plus':
            user_activities = user_activities.filter(distance__gte=DIST_100K)

    # 3. Is Race Filter
    selected_is_race = request.GET.get('is_race')
    if selected_is_race == 'true':
        user_activities = user_activities.filter(is_race=True)


    selected_sort_by = request.GET.get('sort_by', 'start_date_local') # 默认按日期排序
    selected_order = request.GET.get('order', 'desc') # 默认降序

    if selected_order == 'desc':
        user_activities = user_activities.order_by(f'-{selected_sort_by}')
    else:
        user_activities = user_activities.order_by(selected_sort_by)

    # --- Pagination Logic ---
    paginator = Paginator(user_activities, 20)  # 每页显示 20 条活动
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    sortable_fields = [
        ('start_date_local', _('Date')),
        ('name', _('Activity Name')),
        ('distance', _('Distance (km)') if request.user.use_metric else _('Distance (mile)')),
        ('elapsed_time', _('Elapsed Time')),
        ('elevation_gain', _('Elevation Gain (m)') if request.user.use_metric else _('Elevation Gain (feet)')),
        ('average_speed', _('Avg. Pace (min/km)') if request.user.use_metric else _('Avg. Pace (min/mile)')),
        ('average_heartrate', _('Avg. HR')),
        ('average_cadence', _('Ave. Cadence'))
    ]

    context = {
        'page_obj': page_obj,
        'available_years': available_years,
        'available_months': available_months,
        'available_weeks': available_weeks,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'selected_week': selected_week,
        'selected_distance': selected_distance,
        'selected_is_race': selected_is_race,
        'selected_sort_by': selected_sort_by,
        'selected_order': selected_order,
        'sortable_fields': sortable_fields,
        'use_metric': request.user.use_metric,
    }
    return render(request, 'strava_web/activities.html', context)

@login_required
def races(request):
    """
    Displays a blank page for user's race activities.
    """
    # In the future, you would fetch and filter race activities here,
    # similar to how activities_page fetches all activities.
    context = {}
    return render(request, 'strava_web/races.html', context)

@user_passes_test(lambda user: user.is_superuser)
def groups(request):
    """
    Displays a blank page for group management.
    """
    # In the future, you would fetch and filter race activities here,
    # similar to how activities_page fetches all activities.
    context = {}
    return render(request, 'strava_web/groups.html', context)

@user_passes_test(lambda user: user.is_superuser)
def users(request):
    """
    Displays a blank page for group management.
    """
    # In the future, you would fetch and filter race activities here,
    # similar to how activities_page fetches all activities.
    context = {}
    return render(request, 'strava_web/users.html', context)

@login_required
@require_POST # 只允许 POST 请求
def update_activity_ajax(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)
    form = ActivityEditForm(request.POST, instance=activity)

    if form.is_valid():
        # 处理 chip_time 逻辑：如果 is_race 为 True 且 chip_time 为空或 0，则使用 elapsed_time
        if form.cleaned_data['is_race'] and (form.cleaned_data['chip_time'] is None or form.cleaned_data['chip_time'] == 0):
            form.instance.chip_time = activity.elapsed_time # 使用原始活动的 elapsed_time
        activity = form.save() # 保存到数据库

        # 返回更新后的数据，用于前端刷新行
        return JsonResponse({
            'success': True,
            'message': _("Activity updated successfully!"),
            'activity_data': {
                'id': activity.id,
                'name': activity.name,
                'distance': activity.distance,
                'elapsed_time': activity.elapsed_time,
                'is_race': activity.is_race,
                'chip_time': activity.chip_time,
                'race_distance': activity.race_distance,
                'strava_id': activity.strava_id,
                'start_date_local': activity.start_date_local,
                'strava_url': f"https://www.strava.com/activities/{activity.strava_id}"
            }
        })
    else:
        # 返回表单错误
        errors = form.errors.as_json()
        return JsonResponse({'success': False, 'errors': errors}, status=400)