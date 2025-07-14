# strava_app/management/commands/strava_pull.py

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from strava_web.services import sync_strava_data_for_user # 导入你的数据同步服务
import time

User = get_user_model()

class Command(BaseCommand):
    help = 'Pulls Strava data (stats and race activities) for all connected users.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user_id',
            type=int,
            help='Optional: Sync data for a specific user ID.',
        )
        parser.add_argument(
            '--days',
            type=int,
            default=0,
            help='Optional: Sync data for last n days .',
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        days = options['days']
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
                users_to_sync = [user]
                self.stdout.write(self.style.SUCCESS(f'Attempting to sync data for user ID: {user_id}'))
            except User.DoesNotExist:
                raise CommandError(f'User with ID "{user_id}" does not exist.')
        else:
            # 获取所有已连接 Strava 的用户
            users_to_sync = User.objects.filter(strava_id__isnull=False)
            self.stdout.write(self.style.SUCCESS('Attempting to sync data for all connected Strava users.'))

        if not users_to_sync.exists():
            self.stdout.write(self.style.WARNING('No Strava connected users found to sync.'))
            return

        for user in users_to_sync:
            try:
                self.stdout.write(f'Syncing data for user: {user.username} (Strava ID: {user.strava_id})...')
                sync_strava_data_for_user(user, days)
                self.stdout.write(self.style.SUCCESS(f'Successfully synced data for {user.username}.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to sync data for {user.username}: {e}'))

            # 为了避免触及 Strava API 的速率限制，可以在每次请求后暂停一小段时间
            # 例如，每 10 个用户暂停 1 秒
            time.sleep(0.1) # 短暂暂停，避免连续请求过快

        self.stdout.write(self.style.SUCCESS('Strava data pull completed.'))