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
    用户可以加入或离开开放的组。
    """
    open_groups = Group.objects.filter(is_open=True, has_dashboard=True).exclude(name='admin')
    user_current_groups = request.user.groups.all()

    if request.method == 'POST':
        form = GroupMembershipForm(request.POST, user=request.user)
        if form.is_valid():
            selected_groups = form.cleaned_data['groups']

            # 移除用户从旧组中离开
            for group in user_current_groups:
                if group in open_groups and group not in selected_groups:
                    request.user.groups.remove(group)
                    messages.info(request, f"您已离开组: {group.name}")

            # 添加用户到新选择的组
            for group in selected_groups:
                if group in open_groups and group not in user_current_groups:
                    request.user.groups.add(group)
                    messages.success(request, f"您已加入组: {group.name}")

            return redirect('personal_dashboard')
        else:
            messages.error(request, "请修正表单中的错误。")
    else:
        form = GroupMembershipForm(user=request.user) # 预填充用户已加入的组

    context = {
        'form': form,
        'open_groups': open_groups,
        'user_current_groups': user_current_groups,
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
def group_manage_members(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    # 检查当前用户是否是该群组的管理员
    if group.admin != request.user:
        messages.error(request, "您没有权限管理该组。")
        return redirect('group_dashboard', group_id=group.id) # 重定向回群组 Dashboard

    # 这里可以添加管理成员的逻辑，例如列出成员、移除成员等
    group_members = group.members.all() # 获取所有群组成员

    context = {
        'group': group,
        'group_members': group_members,
        'is_group_admin': True, # 明确表示是管理员
    }
    return render(request, 'strava_web/group_manage_members.html', context) # 你需要创建这个模板

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


