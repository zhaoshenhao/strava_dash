# strava_app/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from .models import CustomUser, Activity, GroupApplication
from unfold.admin import ModelAdmin
from django.utils import timezone

# 自定义用户模型的 Admin
@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin, ModelAdmin):
    # 修改列表显示字段
    list_display = ('username', 'email', 'first_name', 'is_staff', 'strava_id')
    # 修改搜索字段
    search_fields = ('username', 'email', 'first_name', 'strava_id')
    # 过滤器
    list_filter = ('is_staff', 'is_active', 'is_superuser', 'groups')

    # 定义字段集，用于在 Admin 详情页组织字段
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        (('Personal info'), {'fields': ('first_name', 'email')}),
        (('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'), # 重新加入 'groups'
        }),
        (('Important dates'), {'fields': ('last_login', 'date_joined')}),
        ('Strava Info', {'fields': ('strava_id', 'strava_access_token', 'strava_refresh_token', 'strava_token_expires_at', 'last_strava_sync')}),
        ('Strava Run Totals', {'fields': (
            'weekly_run_distance', 'weekly_run_count', 'weekly_run_moving_time', 'weekly_run_elapsed_time', 'weekly_run_elevation_gain', 'weekly_avg_heartrate', 'weekly_max_heartrate',
            'recent_run_distance', 'recent_run_count', 'recent_run_moving_time', 'recent_run_elapsed_time', 'recent_run_elevation_gain', 'recent_avg_heartrate', 'recent_max_heartrate',
            'ytd_run_distance', 'ytd_run_count', 'ytd_run_moving_time', 'ytd_run_elapsed_time', 'ytd_run_elevation_gain',
            'all_time_run_distance', 'all_time_run_count', 'all_time_run_moving_time', 'all_time_run_elapsed_time', 'all_time_run_elevation_gain',
        )}),
    )

# 自定义 Group 的 Admin
# 先取消注册默认的 Group admin
admin.site.unregister(Group)

@admin.register(Group)
class CustomGroupAdmin(ModelAdmin):
    list_display = ('name', 'is_open', 'has_dashboard', 'admin')
    list_filter = ('is_open', 'has_dashboard')
    search_fields = ('name',)
    # 允许在 admin 中编辑这些字段
    fields = ('name', 'is_open', 'has_dashboard', 'admin', 'description', 'announcement', 'permissions') # 确保 permissions 也在里面

@admin.register(Activity)
class ActivityAdmin(ModelAdmin):
    date_hierarchy = 'start_date'
    list_display = ('name', 'user', 'activity_type', 'workout_type', 'is_race', 'start_date_local', 'distance', 'moving_time')
    list_filter = ('activity_type', 'workout_type', 'is_race', 'start_date')
    search_fields = ('name', 'user__username', 'strava_id')
    raw_id_fields = ('user',) # 对于 ForeignKey 字段，使用 raw_id_fields 可以提高性能
    date_hierarchy = 'start_date_local' # 按日期分层显示

# 注册 GroupApplication
@admin.register(GroupApplication)
class GroupApplicationAdmin(ModelAdmin):
    list_display = ('user', 'group', 'status', 'applied_at', 'reviewed_at', 'reviewer')
    list_filter = ('status', 'group')
    search_fields = ('user__username', 'group__name')
    raw_id_fields = ('user', 'group', 'reviewer') # 使用 raw_id_fields 提高性能
    readonly_fields = ('applied_at',) # 申请时间自动生成，不允许手动修改
    actions = ['approve_applications', 'reject_applications'] # 添加批量操作

    def approve_applications(self, request, queryset):
        # 批量批准申请
        for application in queryset:
            if application.status == 'pending':
                application.status = 'approved'
                application.reviewed_at = timezone.now()
                application.reviewer = request.user
                application.save()
                # 将用户添加到群组
                application.group.members.add(application.user)
        self.message_user(request, "选定的申请已批准。")
    approve_applications.short_description = "批准选定的申请"

    def reject_applications(self, request, queryset):
        # 批量拒绝申请
        for application in queryset:
            if application.status == 'pending':
                application.status = 'rejected'
                application.reviewed_at = timezone.now()
                application.reviewer = request.user
                application.save()
        self.message_user(request, "选定的申请已拒绝。")
    reject_applications.short_description = "拒绝选定的申请"