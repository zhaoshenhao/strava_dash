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
    path('activities/', views.activities, name='activities'),
    path('races/', views.races, name='races'),

    # 用户信息修改页面
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('profile/password_change/', auth_views.PasswordChangeView.as_view(
        template_name='strava_web/password_change_form.html',
        success_url='/dashboard/' # 修改密码成功后重定向
    ), name='password_change'),
    path('profile/group_membership/', views.group_membership_edit, name='group_membership_edit'), # 个人的组修改页面

    path('users/', views.users, name='users'),
    
    path('groups/', views.groups, name='groups'),
    path('groups/edit/', views.group_membership_edit, name='group_membership_edit'),
    path('groups/<int:group_id>/dashboard/', views.group_dashboard, name='group_dashboard'),
    path('groups/<int:group_id>/manage_members/', views.group_manage_members, name='group_manage_members'),
    path('groups/<int:group_id>/apply/', views.apply_for_group, name='apply_for_group'),
    path('application/<int:application_id>/review/', views.review_group_application, name='review_group_application'),
    path('groups/<int:group_id>/join/', views.join_group, name='join_group'),
    path('groups/<int:group_id>/leave/', views.leave_group, name='leave_group'),
]