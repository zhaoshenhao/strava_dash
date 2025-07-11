# strava_web/urls.py

from django.urls import path
from . import views
from django.contrib.auth import views as auth_views # 导入 Django 认证视图
from .views import CustomLogoutView # 导入我们自定义的 CustomLogoutView

urlpatterns = [
    # Home Page 路由
    path('', views.home, name='home'), # 设置为空路径作为首页
    
    # Strava SSO 认证路由
    path('login/strava/', views.strava_login, name='strava_login'),
    path('oauth/strava/callback/', views.strava_callback, name='strava_callback'),

    # 传统登录、登出路由
    path('login/', auth_views.LoginView.as_view(template_name='strava_web/login.html'), name='login'),
    path('logout/', CustomLogoutView.as_view(), name='logout'), # 使用 CustomLogoutView

    # 注册路由 (Strava SSO 注册会处理大部分逻辑)
    path('register/', views.register_user, name='register'), # Strava SSO 注册后完善信息

    # 用户个人 Dashboard
    path('dashboard/', views.personal_dashboard, name='personal_dashboard'),

    # 用户信息修改页面
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/password_change/', auth_views.PasswordChangeView.as_view(
        template_name='strava_web/password_change_form.html',
        success_url='/dashboard/' # 修改密码成功后重定向
    ), name='password_change'),
    path('profile/group_membership/', views.group_membership_edit, name='group_membership_edit'),

    # 组群 Dashboard (待实现)
    path('groups/<int:group_id>/dashboard/', views.group_dashboard, name='group_dashboard'),
    path('groups/join/<int:group_id>/', views.join_group, name='join_group'),
    path('groups/leave/<int:group_id>/', views.leave_group, name='leave_group'),
]