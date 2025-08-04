from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import Group
from .models import GroupApplication
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from .utils_group import get_groups

def is_admin_or_staff(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)

@login_required
def group_membership_edit(request):
    return get_groups(request, 1)

@login_required
def group_dashboard(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not group.has_dashboard:
        messages.error(request, "该组没有独立的 Dashboard。")
        return redirect('personal_dashboard')

    if not request.user.groups.filter(id=group.id).exists():
        messages.error(request, "您没有权限查看该组的 Dashboard。")
        return redirect('personal_dashboard')

    # 检查当前用户是否是该群组的管理员
    is_group_admin = (group.admin == request.user)
    
    context = {
        'group': group,
        'is_group_admin': is_group_admin, # 将管理员状态传递给模板
        # 这里将是组群排行数据，待实现
    }
    return render(request, 'strava_web/group_dashboard.html', context)

# 新增：申请加入封闭组
@login_required
@require_http_methods(["POST"])
def apply_for_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if group.is_open:
        messages.error(request, _("This is an open group and no application is required to join."))
        return redirect('group_membership_edit')

    if request.user.groups.filter(id=group.id).exists():
        messages.info(request, _("You are already a member of this group."))
        return redirect('group_membership_edit')

    # 检查是否有待处理或被拒绝但未过期的申请
    existing_application = GroupApplication.objects.filter(user=request.user, group=group).first()
    if existing_application:
        if existing_application.status == 'pending':
            messages.info(request, _("You have submitted your application, please wait for the administrator to review it."))
        elif existing_application.status == 'rejected' and \
             existing_application.reviewed_at and (timezone.now() - existing_application.reviewed_at).days < 7:
            messages.warning(request, _("Your application was recently rejected, please try again in 7 days."))
        else: # 超过7天，可以重新申请
            existing_application.delete() # 删除旧的被拒绝申请以便创建新的
            GroupApplication.objects.create(user=request.user, group=group, status='pending')
            messages.success(request, _("Application to join %(group_name)s submitted, please wait for admin review.") % {'group_name': group.name})
            return redirect('group_membership_edit')
        return redirect('group_membership_edit')


    # 创建新的申请
    GroupApplication.objects.create(user=request.user, group=group, status='pending')
    messages.success(request, _("Application to join %(group_name)s submitted, please wait for admin review.") % {'group_name': group.name})
    return redirect('group_membership_edit')


# 新增：群组管理员审核申请
@staff_member_required
@require_http_methods(["POST"])
def review_group_application(request, application_id):
    application = get_object_or_404(GroupApplication, id=application_id)
    group = application.group

    # 检查当前用户是否是该群组的管理员
    if group.admin != request.user:
        messages.error(request, _("You do not have permission to review this request."))
        return redirect('group_dashboard', group_id=group.id)

    action = request.POST.get('action') # 'approve' 或 'reject'

    if application.status != 'pending':
        messages.warning(request, _("The application has been processed."))
        return redirect('group_manage_members', group_id=group.id)

    if action == 'approve':
        application.status = 'approved'
        application.reviewed_at = timezone.now()
        application.reviewer = request.user
        application.save()
        group.members.add(application.user) # 将用户添加到群组
        messages.success(request, _("Approved %(username)s to join %(group_name)s.") % {'username': application.user.username,'group_name': group.name})
    elif action == 'reject':
        application.status = 'rejected'
        application.reviewed_at = timezone.now()
        application.reviewer = request.user
        application.save()
        messages.info(request, _("Rejected %(username)s from joining %(group_name)s.") % {'username': application.user.username,'group_name': group.name})
    else:
        messages.error(request, _("Invalid operation."))

    return redirect('group_manage_members', group_id=group.id)

@login_required
def join_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if group.is_open and group.has_dashboard and group.name != 'admin':
        if not request.user.groups.filter(id=group.id).exists():
            request.user.groups.add(group)
            messages.success(request, _("You have joined the group: %(gname)s.") % {'gname': group.name})
        else:
            messages.info(request, _("You are already in this group:%(gname)s.") % {'gname': group.name})
    else:
        messages.error(request, _("Group %(gname)s is not open.") % {'gname': group.name})
    return redirect('group_membership_edit') # 或重定向到组列表页面

@login_required
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user.groups.filter(id=group.id).exists():
        request.user.groups.remove(group)
        messages.success(request, _("You have left the group: %(gname)s") % {'gname': group.name})
    else:
        messages.info(request, _("You do not belong to this group: %(gname)s") % {'gname': group.name})
    return redirect('group_membership_edit') # 或重定向到组列表页面

@login_required
@user_passes_test(is_admin_or_staff, login_url='/')
def groups(request):
    return get_groups(request, 0)

@login_required
@user_passes_test(is_admin_or_staff, login_url='/')
def group_edit(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    # 权限检查：确保 staff 只能编辑自己管理的组
    if request.user.is_staff and not request.user.is_superuser and group.admin != request.user:
        messages.error(request, _("You do not have permission to edit this group."))
        return redirect('groups')

    # TODO: 在这里添加处理表单提交的逻辑

    context = {
        'group': group,
    }
    return render(request, 'strava_web/group_edit.html', context)

@login_required
@user_passes_test(is_admin_or_staff, login_url='/')
def group_manage_members(request, group_id):
    group = get_object_or_404(Group, id=group_id)

    if group.admin != request.user:
        messages.error(request, _("You do not have permission to manage this group."))
        return redirect('group_dashboard', group_id=group.id)

    # 获取所有群组成员
    group_members = group.members.all()

    # 获取待处理的申请
    pending_applications = GroupApplication.objects.filter(group=group, status='pending')

    context = {
        'group': group,
        'group_members': group_members,
        'pending_applications': pending_applications, # 传递待处理申请
        'is_group_admin': True,
    }
    return render(request, 'strava_web/group_manage_members.html', context)
