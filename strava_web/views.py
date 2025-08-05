from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from .forms import CustomUserProfileForm 
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.views import LogoutView
from .forms import CustomUserProfileForm
from django.http import JsonResponse
from django.db.models.functions import Concat
from django.contrib.auth.models import User
from django.db.models import Q, Value as V, F
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def personal_dashboard(request):
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

@user_passes_test(lambda user: user.is_superuser)
def users(request):
    """
    Displays a blank page for group management.
    """
    # In the future, you would fetch and filter race activities here,
    # similar to how activities_page fetches all activities.
    context = {}
    return render(request, 'strava_web/users.html', context)

def home(request):
    return render(request, 'strava_web/home.html')

class CustomLogoutView(LogoutView):
    next_page = 'home' #

@login_required
def search_users_ajax(request):
    query = request.GET.get('q', '')
    users = User.objects.all()

    if query:
        # 使用 Q 对象组合 OR 查询
        users = users.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        )

    # 按用户全名排序：username (first_name last_name)
    # 我们首先用 Concat 创建一个可排序的字符串
    users = users.annotate(
        full_name=Concat(
            'username', V(' ('), F('first_name'), V(' '), F('last_name'), V(')')
        )
    ).order_by('full_name')

    # 准备返回的 JSON 列表
    results = [
        {
            'id': user.id,
            'text': f"{user.username} ({user.first_name} {user.last_name})"
        }
        for user in users
    ]

    return JsonResponse({'results': results})
