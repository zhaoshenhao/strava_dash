from django.contrib.auth.models import AbstractUser, Group
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.translation import gettext_lazy as _

class CustomUser(AbstractUser):
    # Strava ID: 用于唯一标识 Strava 用户，允许为空以支持非 Strava 登录
    strava_id = models.BigIntegerField(unique=True, null=True, blank=True,
                                       verbose_name=_("Strava ID"),
                                       help_text=_("The unique identifier for the user's Strava account."))

    # Strava OAuth 令牌信息：用于 API 访问和刷新
    strava_access_token = models.CharField(max_length=255, null=True, blank=True,
                                           verbose_name=_("Strava Access Token"),
                                           help_text=_("OAuth 2.0 Access Token for Strava API calls."))
    strava_refresh_token = models.CharField(max_length=255, null=True, blank=True,
                                            verbose_name=_("Strava Refresh Token"),
                                            help_text=_("OAuth 2.0 Refresh Token for obtaining new access tokens."))
    # access_token 的过期时间，用于判断是否需要刷新
    strava_token_expires_at = models.DateTimeField(null=True, blank=True,
                                                  verbose_name=_("Token Expiration"),
                                                  help_text=_("UTC timestamp when the Strava access token expires."))

    # 用户在 Strava SSO 注册时输入的邮件地址（Django AbstractUser 默认已包含 email 字段）
    # 这里确保 email 字段可以为空，但如果通过 SSO 注册，我们要求必填
    # 如果你希望 email 始终唯一，则保持 unique=True
    email = models.EmailField(unique=True, blank=True,
                              verbose_name=_("Email")) # 默认是 unique=True, blank=True

    # 最近一次 Strava 数据同步时间，用于增量更新
    last_strava_sync = models.DateTimeField(null=True, blank=True,
                                            verbose_name=_("Last Strava Sync"),
                                            help_text=_("Last time user's Strava data was synced."))

    # ----- 聚合统计数据 (可以直接存在用户表，或单独的统计表) -----
    # 近期跑步统计 (Last 4 Weeks) - Strava API 中的 recent_run_totals
    recent_run_distance = models.FloatField(default=0.0, verbose_name=_('4 Weeks Distance'))
    recent_run_count = models.IntegerField(default=0, verbose_name=_('4 Weeks Activity Count'))
    recent_run_moving_time = models.IntegerField(default=0, verbose_name=_('4 Weeks MovingTime'))
    recent_run_elapsed_time = models.IntegerField(default=0, verbose_name=_('4 Weeks Elapsed Time'))
    recent_run_elevation_gain = models.FloatField(default=0, verbose_name=_('4 Weeks Elevation Gain'))
    recent_avg_heartrate = models.FloatField(default=0.0, verbose_name=_('4 Weeks Average Heart Rate'))
    recent_max_heartrate = models.FloatField(default=0.0, verbose_name=_('4 Weeks Max Heart Rate'))
    
    # 年度至今跑步统计 (Year To Date) - Strava API 中的 ytd_run_totals
    ytd_run_distance = models.FloatField(default=0.0, verbose_name=_('Year To Date Distance'))
    ytd_run_count = models.IntegerField(default=0, verbose_name=_('Year To Date Activity Count'))
    ytd_run_moving_time = models.IntegerField(default=0, verbose_name=_('Year To Date Movming Time'))
    ytd_run_elapsed_time = models.IntegerField(default=0, verbose_name=_('Year To Date Elapsed Time'))
    ytd_run_elevation_gain = models.FloatField(default=0, verbose_name=_('Year To Date Elevation Gain'))

    # 历史总跑步统计 (All Time) - Strava API 中的 all_run_totals
    all_time_run_distance = models.FloatField(default=0, verbose_name=_('All Time Distance'))
    all_time_run_count = models.IntegerField(default=0, verbose_name=_('All Time Activity Count'))
    all_time_run_moving_time = models.IntegerField(default=0, verbose_name=_('All Time Moving Time'))
    all_time_run_elapsed_time = models.IntegerField(default=0, verbose_name=_('All Time Elapsed Time'))
    all_time_run_elevation_gain = models.FloatField(default=0, verbose_name=_('All Time Elevation Gain'))

    # 最近一周跑步统计数据 (从周日开始计算)
    weekly_run_distance = models.FloatField(default=0.0, verbose_name=_('Weekly Distance'))
    weekly_run_count = models.IntegerField(default=0, verbose_name=_('Weekly Activity Count'))
    weekly_run_moving_time = models.IntegerField(default=0, verbose_name=_('Weekly Moving Time'))
    weekly_run_elapsed_time = models.IntegerField(default=0, verbose_name=_('Weekly Elapsed Time'))
    weekly_run_elevation_gain = models.FloatField(default=0.0, verbose_name=_('Weekly Elevation Gain'))
    weekly_avg_heartrate = models.FloatField(default=0.0, verbose_name=_('Weekly Average Heart Rate'))
    weekly_max_heartrate = models.FloatField(default=0.0, verbose_name=_('Weekly Max Heart Rate'))
    
    use_metric = models.BooleanField(default=True, verbose_name=_("Use Metric System"))
    birth_year = models.IntegerField(null=True, blank=True, verbose_name=_("Birth Year"))

    GENDER_CHOICES = [
        ('M', _('Male')),
        ('F', _('Female')),
    ]
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True, verbose_name=_("Gender"))

    groups = models.ManyToManyField(
        Group,
        related_name='members', # related_name 仍然指向 Group 的成员
        related_query_name='member',
        blank=True,
        help_text=_('The groups this user belongs to. A user will get all permissions '
                   'granted to each of their groups.'),
        verbose_name=_('Groups'),
    )

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        # 定义自定义权限
        permissions = [
            ("can_sync_strava_data", _("Can sync Strava data")),
            ("can_view_strava_reports", _("Can view Strava reports")),
        ]

    def __str__(self):
        if self.username:
            return self.username
        if self.strava_id:
            return f"Strava User {self.strava_id}"
        return super().__str__()

    @property
    def is_strava_connected(self):
        return self.strava_id is not None

    def get_strava_access_token(self):
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
Group.add_to_class('is_open', models.BooleanField(default=True, verbose_name=_("Allow Free Join"),
                                                help_text=_("If checked, users can freely join this group.")))
Group.add_to_class('has_dashboard', models.BooleanField(default=True, verbose_name=_("Has Dashboard"),
                                                        help_text=_("If checked, this group has a dedicated data dashboard.")))
# admin 字段，指向 CustomUser，表示该群组的管理员
# on_delete=models.SET_NULL 表示如果管理员用户被删除，该群组的 admin 字段会设为 NULL
# related_name='administered_groups' 允许通过 user.administered_groups.all() 获取该用户管理的所有群组
Group.add_to_class('admin', models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='administered_groups',
    verbose_name=_("Group Admin"),
    help_text=_("The designated administrator for this group (if any)."),
))
Group.add_to_class('description', models.TextField(
    max_length=500,
    blank=True,
    verbose_name=_("Group Description"),
    help_text=_("Group description in detail. Max length 500 chars."
)))
# announcement 字段
Group.add_to_class('announcement', models.TextField(
    max_length=1000, # 公告通常不宜过长
    blank=True,
    verbose_name=_("Group Announcement"),
    help_text=_("Group announcement. Max length 1000 chars"),
))

# GroupApplication 模型
class GroupApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', _('Pending')),
        ('approved', _('Approved')),
        ('rejected', _('Rejected')),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_applications', verbose_name=_("Requestor"))
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='applications', verbose_name=_("Application"))
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name=_("Status"))
    applied_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Applied At"))
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("Reviewd At"))
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_applications', verbose_name=_("Approver"))

    class Meta:
        unique_together = ('user', 'group') # 确保一个用户只能对一个群组有一个申请
        ordering = ['-applied_at']
        verbose_name = _("Application")
        verbose_name_plural = _("Applications")

    def __str__(self):
        return f"{self.user.username} {_('Request to join')} {self.group.name} - {_('Status')}: {self.get_status_display()}"

# Activity 模型 (用于存储 Strava 活动数据)
class Activity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='strava_activities')
    strava_id = models.BigIntegerField(unique=True, db_index=True, verbose_name=_("Strava Activity ID"))

    name = models.CharField(max_length=255, verbose_name=_("Activity Name"))
    activity_type = models.CharField(max_length=50, verbose_name=_("Activity Type")) # 'Run', 'Ride' etc.
    workout_type = models.IntegerField(null=True, blank=True, verbose_name=_("Workout Type")) # 1 for Race, etc.

    distance = models.FloatField(verbose_name=_("Distance (meters)"))
    moving_time = models.IntegerField(verbose_name=_("Moving Time (seconds)"))
    elapsed_time = models.IntegerField(verbose_name=_("Elapsed Time (seconds)"))
    chip_time = models.IntegerField(default=0, verbose_name=_("Chip Time (seconds)"))
    elevation_gain = models.FloatField(verbose_name=_("Elevation Gain (meters)"))

    start_date = models.DateTimeField(verbose_name=_("Start Date (UTC)"))
    start_date_local = models.DateTimeField(verbose_name=_("Start Date (Local)"))
    timezone = models.CharField(max_length=50, verbose_name=_("Timezone"))

    average_speed = models.FloatField(null=True, blank=True, verbose_name=_("Average Speed (m/s)"))
    max_speed = models.FloatField(null=True, blank=True, verbose_name=_("Max Speed (m/s)"))

    average_heartrate = models.FloatField(null=True, blank=True, verbose_name=_("Average Heartrate (bpm)"))
    max_heartrate = models.FloatField(null=True, blank=True, verbose_name=_("Max Heartrate (bpm)"))
    average_cadence = models.FloatField(null=True, blank=True, verbose_name=_("Average Cadence (steps/min)"))

    has_heartrate = models.BooleanField(default=False, verbose_name=_("Has Heartrate Data"))
    has_power = models.BooleanField(default=False, verbose_name=_("Has Power Data"))

    # 比赛特定的额外字段
    is_race = models.BooleanField(default=False, verbose_name=_("Is Race")) # 方便快速筛选比赛，根据 workout_type=1 设置

    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Created At"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Updated AT"))
    RACE_DISTANCE_CHOINCE = [
        ("1km", _("1 km")),
        ("1mi", _("1 mile")),
        ("5km", _("5 km")),
        ("5mi", _("5 mile")),
        ("10km", _("10 km")),
        ("15km", _("15 km")),
        ("10mi", _("10 mile")),
        ("HM", _("Half Marathon")),
        ("30km", _("30 km")),
        ("FM", _("Marathon")),
        ("50km", _("50 km")),
        ("100km", _("100 km")), 
        ("150km", _("150 km")), 
        ("100mi", _("100 mile")),
        ("Other", _("Other")),
    ]
    race_distance = models.CharField(max_length=50, choices=RACE_DISTANCE_CHOINCE, null=True, blank=True, verbose_name=_("Race Distance"))

    class Meta:
        ordering = ['-start_date_local'] # 默认按日期倒序
        unique_together = ('user', 'strava_id')
        verbose_name = _("Activity")
        verbose_name_plural = _("Activities")

    def __str__(self):
        return f"{self.user.username}'s {self.activity_type} on {self.start_date_local.strftime('%Y-%m-%d')} - {self.name}"
    
