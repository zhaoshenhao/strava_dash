from django.contrib.auth.models import Group
from .models import GroupApplication
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Q, OuterRef, Exists, Subquery
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render

def get_groups(request, mode: 0):
    """
    mode 0: group management list, 1: profile group
    """
    groups_list = Group.objects.filter(has_dashboard=True).exclude(name='admin')
    if mode == 0:
        if request.user.is_superuser: # Admin 用户
            groups_list = Group.objects.filter(admin=request.user)
        groups_list = groups_list.annotate(
            member_count=Count('member', distinct=True),
            request_count=Count('applications', distinct=True, filter=Q(applications__status='pending'))
        )
    elif mode == 1:
        last_application_subquery = GroupApplication.objects.filter(
            group=OuterRef('pk'), # 'OuterRef' links this subquery to the outer Group queryset
            user=request.user       # Filters for the specific user
        ).order_by('-applied_at')[:1]
        groups_list = groups_list.annotate(
            member_count=Count('member', distinct=True),
            is_member=Exists(
                Group.objects.filter(pk=OuterRef('pk'), member=request.user)
            ),
            last_application_id=Subquery(last_application_subquery.values('id')),
            last_application_status=Subquery(last_application_subquery.values('status')),
            last_application_applied_at=Subquery(last_application_subquery.values('applied_at'))
        )
    
    search_query = request.GET.get('search-input', '')
    if search_query:
        groups_list = groups_list.filter(
            Q(name__icontains=search_query) |
            Q(announcement__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(admin__first_name__icontains=search_query) |
            Q(admin__last_name__icontains=search_query) |
            Q(admin__username__icontains=search_query)
        )
    group_type_filter = request.GET.get('group_type_filter', '')
    if group_type_filter:
        if group_type_filter == 'open':
            groups_list = groups_list.filter(is_open=True)
        elif group_type_filter == 'closed':
            groups_list = groups_list.filter(is_open=False)
    
    if mode == 0:
        sortable_fields = [
            ('name',_('Name')),
            ('is_open',_('Type')),
            ('admin__first_name',_('Admin')),
            ('member_count',_('Members')),
            ('request_count',_('Requests')),
        ]
    elif mode == 1:
        is_member_filter = request.GET.get('is_member_filter', '')
        if is_member_filter:
            if is_member_filter == 'yes':
                groups_list = groups_list.filter(is_member=True)
            elif is_member_filter == 'no':
                groups_list = groups_list.filter(is_member=False)
        sortable_fields = [
            ('name',_('Name')),
            ('is_open',_('Type')),
            ('admin__first_name',_('Admin')),
            ('member_count',_('Members')),
            ('is_member',_('Membership')),
        ]


    # 排序逻辑
    sort_by = request.GET.get('sort_by', 'name')
    sort_order = request.GET.get('order', 'asc')
    if sort_by == 'admin__first_name': # 排序管理员姓名
        sort_field = f'-admin__first_name' if sort_order == 'desc' else 'admin__first_name'
        groups_list = groups_list.order_by(sort_field, 'admin__last_name')
    else:
        sort_field = f'-{sort_by}' if sort_order == 'desc' else sort_by
        groups_list = groups_list.order_by(sort_field)

    paginator = Paginator(groups_list, 20) # 每页20行
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    if mode == 0:
        context = {
            'page_obj': page_obj,
            'group_type_filter': group_type_filter,
            'search_query': search_query,
            'sort_by': sort_by,
            'sort_order': sort_order,
            'sortable_fields': sortable_fields,
        }
        return render(request, 'strava_web/groups.html', context)
    elif mode == 1:
        context = {
            'page_obj': page_obj,
            'search_query': search_query,
            'group_type_filter': group_type_filter, # 传递新的过滤参数
            'is_member_filter': is_member_filter,   # 传递新的过滤参数
            'sort_by': sort_by,
            'sort_order': sort_order,
            'sortable_fields': sortable_fields,
        }
        return render(request, 'strava_web/group_membership_edit.html', context)
