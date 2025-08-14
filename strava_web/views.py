from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.views import LogoutView
from .forms import CustomUserProfileForm, CustomUserProfileAdminForm
from django.http import JsonResponse
from django.db.models.functions import Concat
from django.contrib.auth.models import User
from django.db.models import Q, Value as V, F
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from .utils import get_next_url
from django.contrib.auth.forms import SetPasswordForm
from .models import CustomUser

User = get_user_model()

@login_required
def personal_dashboard(request):
    # 可以从 request.user 获取个人信息
    user_groups = request.user.groups.all()
    context = {
        'user': request.user,
        'user_groups': user_groups,
    }
    return render(request, 'strava_web/personal_dashboard.html', context)

@login_required
def profile_self_edit(request):
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

@user_passes_test(lambda user: user.is_superuser)
def profile_admin_edit(request, profile_id):
    user = get_object_or_404(CustomUser, id=profile_id)
    next_url = get_next_url(request, 'personal_dashboard')
    if request.method == 'POST':
        form = CustomUserProfileAdminForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, _("You profile has been updated."))
            return redirect(next_url)
        else:
            messages.error(request, _("Please correct the error in the form."))
    else:
        form = CustomUserProfileAdminForm(instance=user)
    context = {'form': form, 'next_url': next_url, 'is_admin': True}
    return render(request, 'strava_web/profile_edit.html', context)

@user_passes_test(lambda user: user.is_superuser)
def profiles(request):
    profiles_list_qs = CustomUser.objects.all().order_by('username')

    # --- 搜索和筛选逻辑 ---
    search_query = request.GET.get('search', '')
    if search_query:
        profiles_list_qs = profiles_list_qs.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(birth_year__icontains=search_query)
        )

    # 布尔和枚举类型筛选：'true' 为是, 'false' 为否, '' 为不过滤
    is_superuser_filter = request.GET.get('is_superuser', '')
    if is_superuser_filter:
        profiles_list_qs = profiles_list_qs.filter(is_superuser=(is_superuser_filter == 'true'))

    is_staff_filter = request.GET.get('is_staff', '')
    if is_staff_filter:
        profiles_list_qs = profiles_list_qs.filter(is_staff=(is_staff_filter == 'true'))

    is_active_filter = request.GET.get('is_active', '')
    if is_active_filter:
        profiles_list_qs = profiles_list_qs.filter(is_active=(is_active_filter == 'true'))

    gender_filter = request.GET.get('gender', '')
    if gender_filter:
        profiles_list_qs = profiles_list_qs.filter(gender=gender_filter)

    # --- 排序逻辑 ---
    sort_by = request.GET.get('sort_by', 'id')
    sort_order = request.GET.get('sort_order', 'asc')

    valid_sort_fields = [
        'username', 'is_superuser', 'is_staff', 'is_active',
        'first_name', 'email', 'date_joined',
        'birth_year', 'gender'
    ]
    if sort_by in valid_sort_fields:
        if sort_order == 'desc':
            profiles_list_qs = profiles_list_qs.order_by(f'-{sort_by}')
        else:
            profiles_list_qs = profiles_list_qs.order_by(sort_by)

    # --- 分页逻辑 ---
    paginator = Paginator(profiles_list_qs, 10) # 每页显示 10 个档案
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'profiles': page_obj.object_list,
        'search_query': search_query,
        'is_superuser_filter': is_superuser_filter,
        'is_staff_filter': is_staff_filter,
        'is_active_filter': is_active_filter,
        'gender_filter': gender_filter,
        'sort_by': sort_by,
        'sort_order': sort_order,
    }
    return render(request, 'strava_web/profiles.html', context)

def home(request):
    return render(request, 'strava_web/home.html')

class CustomLogoutView(LogoutView):
    next_page = 'home' #

@login_required
def search_users_ajax(request):
    query = request.GET.get('q', '')
    users = User.objects.filter(is_active=True)

    if query:
        # 使用 Q 对象组合 OR 查询
        users = users.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query)
        )
    # 按用户全名排序：username (first_name)
    # 我们首先用 Concat 创建一个可排序的字符串
    users = users.annotate(
        full_name=Concat(
            'username', V(' ('), F('first_name'), V(' '), V(')')
        )
    ).order_by('full_name')
    # 准备返回的 JSON 列表
    results = [
        {
            'id': user.id,
            'text': f"{user.username} ({user.first_name})"
        }
        for user in users
    ]
    return JsonResponse({'results': results})

@user_passes_test(lambda user: user.is_superuser)
def profile_password_change(request, profile_id):
    profile_to_reset = get_object_or_404(User, pk=profile_id)
    next_url = get_next_url(request, 'profiles')
    if request.method == 'POST':
        form = SetPasswordForm(profile_to_reset, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _(f"Password for user '{profile_to_reset.username}' has been reset successfully."))
            return redirect('next_url')
        else:
            # 如果表单验证失败，messages.error 可以展示通用的错误信息
            messages.error(request, _("Please correct the errors below."))
    else:
        form = SetPasswordForm(profile_to_reset)

    context = {
        'profile_to_reset': profile_to_reset,
        'form': form,
        'next_url': next_url,
    }
    return render(request, 'strava_web/profile_password_change.html', context)