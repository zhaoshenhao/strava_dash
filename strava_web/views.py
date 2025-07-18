# strava_web/views.py

import requests
import json
from datetime import datetime, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.contrib.auth import login, authenticate, get_user_model
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Group # 导入 Group 模型
from django.contrib.auth.views import LogoutView # 导入 LogoutView
from .forms import StravaUserRegistrationForm, CustomUserProfileForm, GroupMembershipForm # 待创建表单
from .services import refresh_strava_token, sync_strava_data_for_user # 待创建服务
# 用于分页和排序
from .models import GroupApplication
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Q # 用于计数和复杂查询


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
        messages.error(request, "CSRF 验证失败。")
        return HttpResponseRedirect(reverse('login'))
    del request.session['strava_oauth_state'] # 使用后删除

    if error:
        messages.error(request, f"Strava 授权失败: {error}")
        return HttpResponseRedirect(reverse('login'))

    if not code:
        messages.error(request, "未收到 Strava 授权码。")
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
                messages.success(request, f"欢迎加入 Strava Dash，{user.get_full_name() or user.username}！请完善您的注册信息。")
                return HttpResponseRedirect(reverse('register')) # 新用户跳转到完善信息页
            else:
                messages.success(request, f"欢迎回来，{user.get_full_name() or user.username}！")
                return HttpResponseRedirect(reverse('personal_dashboard')) # 登录成功重定向
        else:
            messages.error(request, "Strava 登录失败，请重试。")
            return HttpResponseRedirect(reverse('login'))

    except requests.exceptions.RequestException as e:
        messages.error(request, f"与 Strava 通信失败: {e}")
        return HttpResponseRedirect(reverse('login'))
    except json.JSONDecodeError:
        messages.error(request, "Strava 响应格式错误。")
        return HttpResponseRedirect(reverse('login'))
    except Exception as e:
        messages.error(request, f"登录过程中发生未知错误: {e}")
        return HttpResponseRedirect(reverse('login'))

@login_required
def register_user(request):
    """
    新用户 Strava SSO 注册后，完善邮件和密码信息。
    """
    if request.user.has_usable_password() and request.user.email:
        messages.info(request, "您的注册信息已完善。")
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
            messages.success(request, "注册信息已完善！")
            # 重新登录以更新 session 中的用户认证状态
            login(request, user, backend='django.contrib.auth.backends.ModelBackend') 
            return redirect('personal_dashboard')
        else:
            messages.error(request, "请修正表单中的错误。")
    else:
        form = StravaUserRegistrationForm(instance=request.user) # 预填充 Strava 提供的名字等

    context = {'form': form}
    return render(request, 'strava_web/register.html', context)


@login_required
def personal_dashboard(request):
    """
    显示个人 Dashboard，包含个人信息和加入的组。
    """
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
            messages.success(request, "您的个人信息已更新。")
            return redirect('personal_dashboard')
        else:
            messages.error(request, "请修正表单中的错误。")
    else:
        form = CustomUserProfileForm(instance=request.user)

    context = {'form': form}
    return render(request, 'strava_web/profile_edit.html', context)

@login_required
def group_membership_edit(request):
    """
    用户可以查看所有开放和封闭的组，并进行加入/申请/退出操作。
    """
    # 获取所有有 Dashboard 的组，排除 'admin' 组
    all_groups_queryset = Group.objects.filter(has_dashboard=True).exclude(name='admin') \
                                       .annotate(member_count=Count('member')) # 计算成员数

    # 搜索功能
    search_query = request.GET.get('search', '')
    if search_query:
        all_groups_queryset = all_groups_queryset.filter(
            Q(name__icontains=search_query) |
            Q(admin__username__icontains=search_query)
        )

    # 准备数据以包含群组类型、成员状态和申请状态
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
            action_button_text = "退出"
            action_button_class = "btn-danger"
            action_url_name = "leave_group" # 这是一个新的/修改后的URL，需要JS确认
        elif group.is_open:
            # 如果是开放组且不是成员，显示“加入”按钮
            action_button_text = "加入"
            action_button_class = "btn-success"
            action_url_name = "join_group"
        else:
            # 如果是封闭组且不是成员，处理申请逻辑
            try:
                application = GroupApplication.objects.get(user=request.user, group=group)
                if application.status == 'pending':
                    application_status_display = "等待批准"
                    action_button_text = "等待"
                    action_button_class = "btn-warning"
                    action_button_disabled = True
                elif application.status == 'rejected':
                    # 检查是否在拒绝后7天内
                    if application.reviewed_at and (timezone.now() - application.reviewed_at).days < 7:
                        application_status_display = "已拒绝 (7天内不可重申)"
                        action_button_text = "拒绝"
                        action_button_class = "btn-secondary"
                        action_button_disabled = True
                    else:
                        application_status_display = "已拒绝 (可重新申请)"
                        action_button_text = "申请" # 超过7天可重新申请
                        action_button_class = "btn-primary"
                        is_application_form = True # 标记为申请表单
                        action_url_name = "apply_for_group"
            except GroupApplication.DoesNotExist:
                # 未申请
                application_status_display = "未申请"
                action_button_text = "申请"
                action_button_class = "btn-primary"
                is_application_form = True # 标记为申请表单
                action_url_name = "apply_for_group"

        groups_data.append({
            'group': group,
            'group_type': "开放" if group.is_open else "封闭",
            'is_member': is_member,
            'member_count': group.member_count,
            'application_status_display': application_status_display,
            'action_button_text': action_button_text,
            'action_button_class': action_button_class,
            'action_button_disabled': action_button_disabled,
            'action_url_name': action_url_name,
            'is_application_form': is_application_form,
        })

    # 排序功能
    sort_by = request.GET.get('sort_by', 'name') # 默认按组名排序
    order = request.GET.get('order', 'asc') # 默认升序

    def get_sort_key(item):
        if sort_by == 'name':
            return item['group'].name
        elif sort_by == 'member_count':
            return item['member_count']
        elif sort_by == 'admin':
            return item['group'].admin.username if item['group'].admin else ''
        elif sort_by == 'group_type':
            # 开放在前，封闭在后
            return (0 if item['group'].is_open else 1, item['group'].name)
        elif sort_by == 'is_member':
            # 成员在前，非成员在后
            return (0 if item['is_member'] else 1, item['group'].name)
        return item['group'].name # 默认

    groups_data.sort(key=get_sort_key, reverse=(order == 'desc'))

    # 分页
    page = request.GET.get('page', 1)
    paginator = Paginator(groups_data, 10) # 每页10个
    try:
        groups_paginated = paginator.page(page)
    except PageNotAnInteger:
        groups_paginated = paginator.page(1)
    except EmptyPage:
        groups_paginated = paginator.page(paginator.num_pages)

    context = {
        'groups_paginated': groups_paginated,
        'search_query': search_query,
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
@login_required
@login_required
def group_manage_members(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # 检查当前用户是否是该群组的管理员
    if group.admin != request.user:
        messages.error(request, "您没有权限管理该组。")
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
        messages.error(request, "这是一个开放群组，无需申请即可加入。")
        return redirect('group_membership_edit')

    if request.user.groups.filter(id=group.id).exists():
        messages.info(request, "您已经是该群组的成员。")
        return redirect('group_membership_edit')

    # 检查是否有待处理或被拒绝但未过期的申请
    existing_application = GroupApplication.objects.filter(user=request.user, group=group).first()
    if existing_application:
        if existing_application.status == 'pending':
            messages.info(request, "您已经提交了申请，请等待管理员审核。")
        elif existing_application.status == 'rejected' and \
             existing_application.reviewed_at and (timezone.now() - existing_application.reviewed_at).days < 7:
            messages.warning(request, "您的申请最近被拒绝，请在7天后重试。")
        else: # 超过7天，可以重新申请
            existing_application.delete() # 删除旧的被拒绝申请以便创建新的
            GroupApplication.objects.create(user=request.user, group=group, status='pending')
            messages.success(request, f"已向 {group.name} 提交加入申请，请等待管理员审核。")
            return redirect('group_membership_edit')
        return redirect('group_membership_edit')


    # 创建新的申请
    GroupApplication.objects.create(user=request.user, group=group, status='pending')
    messages.success(request, f"已向 {group.name} 提交加入申请，请等待管理员审核。")
    return redirect('group_membership_edit')


# 新增：群组管理员审核申请
@login_required
@require_http_methods(["POST"])
def review_group_application(request, application_id):
    application = get_object_or_404(GroupApplication, id=application_id)
    group = application.group

    # 检查当前用户是否是该群组的管理员
    if group.admin != request.user:
        messages.error(request, "您没有权限审核此申请。")
        return redirect('group_dashboard', group_id=group.id)

    action = request.POST.get('action') # 'approve' 或 'reject'

    if application.status != 'pending':
        messages.warning(request, "该申请已处理过。")
        return redirect('group_manage_members', group_id=group.id)

    if action == 'approve':
        application.status = 'approved'
        application.reviewed_at = timezone.now()
        application.reviewer = request.user
        application.save()
        group.members.add(application.user) # 将用户添加到群组
        messages.success(request, f"已批准 {application.user.username} 加入 {group.name}。")
    elif action == 'reject':
        application.status = 'rejected'
        application.reviewed_at = timezone.now()
        application.reviewer = request.user
        application.save()
        messages.info(request, f"已拒绝 {application.user.username} 加入 {group.name}。")
    else:
        messages.error(request, "无效的操作。")

    return redirect('group_manage_members', group_id=group.id)

@login_required
def join_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if group.is_open and group.has_dashboard and group.name != 'admin':
        if not request.user.groups.filter(id=group.id).exists():
            request.user.groups.add(group)
            messages.success(request, f"您已加入组: {group.name}")
        else:
            messages.info(request, f"您已在该组中: {group.name}")
    else:
        messages.error(request, f"组 {group.name} 不允许自由加入。")
    return redirect('personal_dashboard') # 或重定向到组列表页面

@login_required
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user.groups.filter(id=group.id).exists():
        request.user.groups.remove(group)
        messages.success(request, f"您已离开组: {group.name}")
    else:
        messages.info(request, f"您不属于该组: {group.name}")
    return redirect('personal_dashboard') # 或重定向到组列表页面

def home(request):
    """
    应用的首页，无需登录即可访问。
    """
    return render(request, 'strava_web/home.html')

class CustomLogoutView(LogoutView):
    next_page = 'home' # 登出后重定向到名为 'home' 的 URL


