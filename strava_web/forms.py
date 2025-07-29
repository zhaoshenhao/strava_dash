# strava_web/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from .models import Activity

User = get_user_model()

class StravaUserRegistrationForm(forms.ModelForm):
    email = forms.EmailField(required=True, label="Email Address")
    password = forms.CharField(label=_("Password"), widget=forms.PasswordInput, required=True)
    password_confirm = forms.CharField(label=_("Confirm Password"), widget=forms.PasswordInput, required=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'use_metric', 'birth_year', 'gender') # 用户名默认由 Strava ID 生成，不可修改

    def clean_email(self):
        email = self.cleaned_data['email']
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(_("This email address has been registered. Please use another email address."))
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', _("Password mismatched"))
        return cleaned_data

class CustomUserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 遍历表单中的所有字段，为它们的部件添加 Bootstrap 的 'form-control' 类
        for field_name, field in self.fields.items():
            # 排除特定类型的 widget，因为 'form-control' 类可能不适用于它们
            # 例如：CheckboxInput, RadioSelect, ClearableFileInput
            if not isinstance(field.widget, (forms.CheckboxInput, forms.RadioSelect, forms.ClearableFileInput)):
                # 检查是否已经有 class 属性，如果有则追加，否则直接设置
                current_classes = field.widget.attrs.get('class', '')
                if current_classes:
                    field.widget.attrs['class'] = current_classes + ' form-control'
                else:
                    field.widget.attrs['class'] = 'form-control'

            # 可选：为特定字段添加 placeholder 属性
            # if field_name == 'first_name':
            #     field.widget.attrs['placeholder'] = _("Enter your first name")
            # if field_name == 'email':
            #     field.widget.attrs['placeholder'] = _("Enter your email address")
            
class GroupMembershipForm(forms.Form):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.filter(is_open=True, has_dashboard=True).exclude(name='admin'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label=_("Please choose the group.")
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

class ActivityEditForm(forms.ModelForm):
    class Meta:
        model = Activity
        # 只包含允许在模态窗口中修改的字段
        fields = ['is_race', 'chip_time', 'race_distance', 'name']
        labels = {
            'is_race': _("Is this a Race?"),
            'chip_time': _("Chip Time"),
            'race_distance': _("Race Distance"),
            'name': _('Activity Name')
        }
        help_texts = {
            'chip_time': _("Your official race finish time in seconds. Leave blank or 0 to use Elapsed Time."),
            'race_distance': _("Official distance of the race."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if not isinstance(field.widget, forms.CheckboxInput): # 排除 Checkbox
                current_classes = field.widget.attrs.get('class', '')
                if current_classes:
                    field.widget.attrs['class'] = current_classes + ' form-control'
                else:
                    field.widget.attrs['class'] = 'form-control'
            # Checkbox 需要不同的样式，或者不需要 form-control
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input' # Bootstrap 样式
                field.label_suffix = '' # 移除复选框标签的冒号

        if self.instance and not self.instance.is_race:
            self.fields['chip_time'].widget.attrs['disabled'] = True
            self.fields['race_distance'].widget.attrs['disabled'] = True
