# strava_web/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group
from .models import GroupApplication

User = get_user_model()

class StravaUserRegistrationForm(forms.ModelForm):
    # 邮箱字段，在注册时是必填项
    email = forms.EmailField(required=True, label="Email Address")
    password = forms.CharField(label="Password", widget=forms.PasswordInput, required=True)
    password_confirm = forms.CharField(label="Confirm Password", widget=forms.PasswordInput, required=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email') # 用户名默认由 Strava ID 生成，不可修改

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("此邮箱已被注册，请使用其他邮箱。")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', "两次输入的密码不一致。")
        return cleaned_data

class CustomUserProfileForm(forms.ModelForm):
    """
    用于用户修改个人信息（不包括密码和组）。
    """
    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email') # 允许用户修改名字和邮件

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 用户名和 Strava ID 不允许通过此表单修改
        if 'username' in self.fields:
            self.fields['username'].widget = forms.HiddenInput()
        if 'strava_id' in self.fields:
            self.fields['strava_id'].widget = forms.HiddenInput()

    def clean_email(self):
        email = self.cleaned_data['email']
        # 确保修改后的 email 不与现有其他用户的 email 冲突
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("此邮箱已被注册，请使用其他邮箱。")
        return email

class GroupMembershipForm(forms.Form):
    """
    用于用户管理其组的加入和退出。
    """
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.filter(is_open=True, has_dashboard=True).exclude(name='admin'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="选择您要加入或退出的组"
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            # 预填充用户已经加入的开放组
            self.fields['groups'].initial = self.user.groups.filter(
                is_open=True, has_dashboard=True
            ).exclude(name='admin')

# 不需要为 GroupApplication 创建一个用于用户提交的表单，因为我们使用按钮触发
# 但可以为管理员审核创建一个简单的表单（如果需要更复杂的审核流程）
# class GroupApplicationReviewForm(forms.ModelForm):
#     class Meta:
#         model = GroupApplication
#         fields = ['status'] # 管理员可以修改状态
#         widgets = {
#             'status': forms.RadioSelect, # 示例：使用单选按钮选择状态
#         }