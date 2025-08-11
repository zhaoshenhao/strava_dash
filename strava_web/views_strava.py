import requests
import json
from datetime import timedelta
from django.shortcuts import render, redirect
from django.urls import reverse
from django.conf import settings
from django.http import HttpResponseRedirect
from django.contrib.auth import login, authenticate, get_user_model
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db import transaction
from .forms import StravaUserRegistrationForm
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
                messages.success(request, f"Welcome to Strava Dash，{user.first_name or user.username}！Please complete your registration.")
                messages.success(request, _("Welcome to Strava Dash, %(username)s! Please complete your registration.") % {'username': user.first_name or user.username})
                return HttpResponseRedirect(reverse('register')) # 新用户跳转到完善信息页
            else:
                messages.success(request, _("Welcome back, %(username)s!") % {'username': user.first_name or user.username})
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
