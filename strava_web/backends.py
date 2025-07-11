# strava_web/backends.py

from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

class StravaAuthBackend(BaseBackend):
    def authenticate(self, request, strava_id=None, username=None, password=None, **kwargs):
        User = get_user_model()

        # 优先通过 strava_id 认证（SSO 流程）
        if strava_id:
            try:
                user = User.objects.get(strava_id=strava_id)
                return user
            except User.DoesNotExist:
                return None

        # 如果提供了 username (或 email) 和 password (传统登录流程)
        if username and password:
            # 尝试通过 username 或 email 登录
            try:
                # 区分用户是输入了用户名还是邮箱
                if '@' in username:
                    user = User.objects.get(email=username)
                else:
                    user = User.objects.get(username=username)
            except User.DoesNotExist:
                return None

            if user.check_password(password) and self.user_can_authenticate(user):
                return user

        return None # 无法认证

    def get_user(self, user_id):
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None

    def user_can_authenticate(self, user):
        """
        Reject users whose accounts are inactive, if the default Django
        ModelBackend does this.
        """
        is_active = getattr(user, 'is_active', True)
        return is_active