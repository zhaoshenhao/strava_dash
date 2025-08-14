# strava_app/management/commands/strava_pull.py
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from strava_web.services import sync_strava_data_for_user
from django.conf import settings
from django.utils import timezone
from datetime import timedelta, datetime
from django.db.models import Q
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
            help='Optional: Sync data for last n days.',
        )
        parser.add_argument(
            '--force',
            action="store_true",
            help='Force update.',
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        days = options['days']
        force = options['force']
        self.stdout.write(self.style.SUCCESS(f'Start the data pulling process at: {datetime.now()}'))
        if user_id:
            try:
                user = User.objects.get(pk=user_id)
                users_to_sync = [user]
                self.stdout.write(self.style.SUCCESS(f'Attempting to sync data for user ID: {user_id}'))
            except User.DoesNotExist:
                raise CommandError(f'User with ID "{user_id}" does not exist.')
        else:
            if force:
                sync_interval_seconds = 0
            else:
                sync_interval_seconds = getattr(settings, 'STRAVA_SYNC_INTERVAL_SECONDS', 3600)
            time_threshold = timezone.now() - timedelta(seconds=sync_interval_seconds)
            users_to_sync = User.objects.filter(strava_id__isnull=False
                ).filter(Q(last_strava_sync__isnull=True) | Q(last_strava_sync__lt=time_threshold))
            self.stdout.write(self.style.SUCCESS('Attempting to sync data for all connected Strava users.'))
        if not users_to_sync.exists():
            self.stdout.write(self.style.WARNING('No Strava connected users found to sync.'))
            return
        for user in users_to_sync:
            try:
                self.stdout.write(f'Syncing data for user: {user.username} (Strava ID: {user.strava_id})...')
                sync_strava_data_for_user(user, days, self.stdout)
                self.stdout.write(self.style.SUCCESS(f'Successfully synced data for {user.username}.'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to sync data for {user.username}: {e}'))

            # 为了避免触及 Strava API 的速率限制，可以在每次请求后暂停一小段时间
            # 例如，每 10 个用户暂停 1 秒
            time.sleep(0.1) # 短暂暂停，避免连续请求过快

        self.stdout.write(self.style.SUCCESS('Strava data pull completed.'))