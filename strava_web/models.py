from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.conf import settings

class CustomUser(AbstractUser):
    # Strava ID: 用于唯一标识 Strava 用户，允许为空以支持非 Strava 登录
    strava_id = models.BigIntegerField(unique=True, null=True, blank=True,
                                       verbose_name="Strava ID",
                                       help_text="The unique identifier for the user's Strava account.")

    # Strava OAuth 令牌信息：用于 API 访问和刷新
    strava_access_token = models.CharField(max_length=255, null=True, blank=True,
                                           verbose_name="Strava Access Token",
                                           help_text="OAuth 2.0 Access Token for Strava API calls.")
    strava_refresh_token = models.CharField(max_length=255, null=True, blank=True,
                                            verbose_name="Strava Refresh Token",
                                            help_text="OAuth 2.0 Refresh Token for obtaining new access tokens.")
    # access_token 的过期时间，用于判断是否需要刷新
    strava_token_expires_at = models.DateTimeField(null=True, blank=True,
                                                  verbose_name="Token Expiration",
                                                  help_text="UTC timestamp when the Strava access token expires.")

    # 用户在 Strava SSO 注册时输入的邮件地址（Django AbstractUser 默认已包含 email 字段）
    # 这里确保 email 字段可以为空，但如果通过 SSO 注册，我们要求必填
    # 如果你希望 email 始终唯一，则保持 unique=True
    email = models.EmailField('email address', unique=True, blank=True) # 默认是 unique=True, blank=True

    # 最近一次 Strava 数据同步时间，用于增量更新
    last_strava_sync = models.DateTimeField(null=True, blank=True,
                                            verbose_name="Last Strava Sync",
                                            help_text="Last time user's Strava data was synced.")

    # ----- 聚合统计数据 (可以直接存在用户表，或单独的统计表) -----
    # 近期跑步统计 (Last 4 Weeks) - Strava API 中的 recent_run_totals
    recent_run_distance = models.FloatField(default=0.0) # 米
    recent_run_count = models.IntegerField(default=0)
    recent_run_moving_time = models.IntegerField(default=0) # 秒
    recent_run_elapsed_time = models.IntegerField(default=0) # 秒
    recent_run_elevation_gain = models.FloatField(default=0) # 米
    recent_avg_heartrate = models.FloatField(default=0.0)
    recent_max_heartrate = models.FloatField(default=0.0)
    
    # 年度至今跑步统计 (Year To Date) - Strava API 中的 ytd_run_totals
    ytd_run_distance = models.FloatField(default=0.0) # 米
    ytd_run_count = models.IntegerField(default=0)
    ytd_run_moving_time = models.IntegerField(default=0) # 秒
    ytd_run_elapsed_time = models.IntegerField(default=0) # 秒
    ytd_run_elevation_gain = models.FloatField(default=0) # 米

    # 历史总跑步统计 (All Time) - Strava API 中的 all_run_totals
    all_time_run_distance = models.FloatField(default=0) # 米
    all_time_run_count = models.IntegerField(default=0)
    all_time_run_moving_time = models.IntegerField(default=0) # 秒
    all_time_run_elapsed_time = models.IntegerField(default=0) # 秒
    all_time_run_elevation_gain = models.FloatField(default=0) # 米

    # 最近一周跑步统计数据 (从周日开始计算)
    weekly_run_distance = models.FloatField(default=0.0) # meters
    weekly_run_count = models.IntegerField(default=0)
    weekly_run_moving_time = models.IntegerField(default=0) # seconds
    weekly_run_elapsed_time = models.IntegerField(default=0) # seconds
    weekly_run_elevation_gain = models.FloatField(default=0.0) # meters
    weekly_avg_heartrate = models.FloatField(default=0.0)
    weekly_max_heartrate = models.FloatField(default=0.0)
    
    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        # 定义自定义权限
        permissions = [
            ("can_sync_strava_data", "Can sync Strava data"),
            ("can_view_strava_reports", "Can view Strava reports"),
        ]

    def __str__(self):
        if self.username:
            return self.username
        if self.strava_id:
            return f"Strava User {self.strava_id}"
        return super().__str__()

    @property
    def is_strava_connected(self):
        """检查用户是否连接了 Strava"""
        return self.strava_id is not None

    def get_strava_access_token(self):
        """
        获取有效的 Strava Access Token。如果过期，尝试刷新。
        """
        if not self.strava_access_token or not self.strava_refresh_token:
            return None

        # 检查是否过期，留出一些余量 (例如，在过期前5分钟刷新)
        if self.strava_token_expires_at and self.strava_token_expires_at < timezone.now() + timezone.timedelta(minutes=5):
            # 令牌已过期或即将过期，尝试刷新
            try:
                # 避免循环导入，在需要时局部导入或在函数外定义服务
                from strava_web.services import refresh_strava_token 
                new_tokens = refresh_strava_token(self)
                self.strava_access_token = new_tokens['access_token']
                self.strava_refresh_token = new_tokens['refresh_token']
                self.strava_token_expires_at = timezone.now() + timezone.timedelta(seconds=new_tokens['expires_in'])
                self.save()
                return self.strava_access_token
            except Exception as e:
                # 刷新失败，需要用户重新授权
                self.strava_access_token = None
                self.strava_refresh_token = None
                self.strava_token_expires_at = None
                self.save()
                raise ValueError(f"Failed to refresh Strava token for user {self.username}: {e}. Please re-authorize.")
        return self.strava_access_token

# 扩展 Django Group 模型，添加组类型字段
Group.add_to_class('is_open', models.BooleanField(default=True, verbose_name="Allow Free Join",
                                                help_text="If checked, users can freely join this group."))
Group.add_to_class('has_dashboard', models.BooleanField(default=True, verbose_name="Has Dashboard",
                                                        help_text="If checked, this group has a dedicated data dashboard."))

# Activity 模型 (用于存储 Strava 活动数据)
class Activity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='strava_activities')
    strava_id = models.BigIntegerField(unique=True, db_index=True, verbose_name="Strava Activity ID")

    name = models.CharField(max_length=255, verbose_name="Activity Name")
    activity_type = models.CharField(max_length=50, verbose_name="Activity Type") # 'Run', 'Ride' etc.
    workout_type = models.IntegerField(null=True, blank=True, verbose_name="Workout Type") # 1 for Race, etc.

    distance = models.FloatField(verbose_name="Distance (meters)")
    moving_time = models.IntegerField(verbose_name="Moving Time (seconds)")
    elapsed_time = models.IntegerField(verbose_name="Elapsed Time (seconds)")
    elevation_gain = models.FloatField(verbose_name="Elevation Gain (meters)")

    start_date = models.DateTimeField(verbose_name="Start Date (UTC)") # 活动开始时间 (UTC)
    start_date_local = models.DateTimeField(verbose_name="Start Date (Local)") # 活动开始时间 (本地时区)
    timezone = models.CharField(max_length=50, verbose_name="Timezone")

    average_speed = models.FloatField(null=True, blank=True, verbose_name="Average Speed (m/s)")
    max_speed = models.FloatField(null=True, blank=True, verbose_name="Max Speed (m/s)")

    average_heartrate = models.FloatField(null=True, blank=True, verbose_name="Average Heartrate (bpm)")
    max_heartrate = models.FloatField(null=True, blank=True, verbose_name="Max Heartrate (bpm)")
    average_cadence = models.FloatField(null=True, blank=True, verbose_name="Average Cadence (steps/min)")

    has_heartrate = models.BooleanField(default=False, verbose_name="Has Heartrate Data")
    has_power = models.BooleanField(default=False, verbose_name="Has Power Data")

    # 比赛特定的额外字段
    is_race = models.BooleanField(default=False, verbose_name="Is Race") # 方便快速筛选比赛，根据 workout_type=1 设置

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date'] # 默认按日期倒序
        verbose_name = "Activity"
        verbose_name_plural = "Activities"

    def __str__(self):
        return f"{self.user.username}'s {self.activity_type} on {self.start_date_local.strftime('%Y-%m-%d')} - {self.name}"