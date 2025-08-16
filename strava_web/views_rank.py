from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import F, Q, ExpressionWrapper, fields, OuterRef, Subquery
from django.db.models.functions import Cast, ExtractYear
from django.core.paginator import Paginator
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from .models import Group, CustomUser, Activity
from django.contrib import messages
from .utils import get_next_url
import datetime
from django.utils import timezone
from datetime import timedelta
from django.db.models import Min

AGE_RANGES = {
    'all': (_('All Ages'), (None, None)),
    '<40': (_('<40 years old'), (None, 39)),
    '40-44': (_('40-44 years old'), (40, 44)),
    '45-49': (_('45-49 years old'), (45, 49)),
    '50-54': (_('50-54 years old'), (50, 54)),
    '55-59': (_('55-59 years old'), (55, 59)),
    '60-64': (_('60-64 years old'), (60, 64)),
    '65-69': (_('65-69 years old'), (65, 69)),
    '70-74': (_('70-74 years old'), (70, 74)),
    '75-79': (_('75-79 years old'), (75, 79)),
    '>=80': (_('>=80 years old'), (80, None)),
}

PERIODS = {
    'weekly': _('This Week'),
    'recent': _('4 Weeks'),
    'ytd': _('YTD'),
    'all_time': _('All Time'),
}

RANK_TYPES = {
    'distance': _('Distance'),
    'moving_time': _('Moving time'),
    'avg_pace': _('Average Pace'),
    'elevation_gain': _('Elevation Gain'),
}

GENDERS = {'all': _('All Genders'), 'M': _('Male'), 'F': _('Female')}

@login_required
def stats_ranking(request, group_id):
    group = get_object_or_404(Group, pk=group_id)
    is_group_member = group.members.filter(pk=request.user.pk).exists()
    is_group_admin = (group.admin == request.user)
    next_url = get_next_url(request, 'groups')
    from django.contrib import messages
    if not (request.user.is_superuser or is_group_member or is_group_admin or group.is_open):
        messages.error(request, _("You do not have permission to view the group dashboard."))
        return redirect('group_membership')
    
    # 1. 从 URL 参数中获取筛选条件
    period = request.GET.get('period', 'weekly')
    gender = request.GET.get('gender', 'all')
    age_range_key = request.GET.get('age', 'all')
    rank_type = request.GET.get('rank_type', 'distance')
    
    ranking_field_map = {
        'distance': f'{period}_run_distance',
        'moving_time': f'{period}_run_moving_time',
        'avg_pace': f'{period}_run_distance',
        'elevation_gain': f'{period}_run_elevation_gain',
    }
    ranking_position = list(ranking_field_map.keys()).index(rank_type) + 3
    ranking_field = ranking_field_map.get(rank_type)
    ranking_field2 = None
    
    if rank_type == 'avg_pace':
        ranking_field2 = f'{period}_run_moving_time'
    
    group_members = CustomUser.objects.filter(groups=group,is_active=True)
    if ranking_field2:
        group_members.exclude(**{ranking_field2: None})
    
    if gender != 'all':
        group_members = group_members.filter(gender=gender)
    
    if age_range_key != 'all' and age_range_key in AGE_RANGES:
        group_members.exclude(Q(birth_year__isnull=True) | Q(birth_year=0))
        start_age, end_age = AGE_RANGES[age_range_key][1]
        current_year = datetime.date.today().year
        q = Q()
        if start_age is not None:
            q &= Q(birth_year__lte=current_year - start_age)
        if end_age is not None:
            q &= Q(birth_year__gte=current_year - end_age)
        group_members = group_members.filter(q)

    if rank_type == 'avg_pace':
        group_members = group_members.annotate(
            avg_pace_value=ExpressionWrapper(
                Cast(F(ranking_field2), output_field=fields.FloatField()) / Cast(F(ranking_field), output_field=fields.FloatField()),
                output_field=fields.FloatField()
            )
        ).order_by('avg_pace_value')
    else:
        group_members = group_members.order_by(F(ranking_field).desc(nulls_last=True))

    paginator = Paginator(group_members, 10)
    page_number = request.GET.get('page', 1)
    
    total_participants = paginator.count
    current_user_rank = None
    
    if is_group_member:
        user_ids = list(group_members.values_list('pk', flat=True))
        try:
            current_user_rank = user_ids.index(request.user.pk) + 1
        except ValueError:
            pass
    
    if is_group_member and current_user_rank:
        page_number_to_show = (current_user_rank - 1) // 10 + 1
    else:
        page_number_to_show = int(page_number)
        
    try:
        page_obj = paginator.page(page_number_to_show)
    except:
        page_obj = paginator.page(1)
    
    members_list = []
    rank = page_obj.start_index()
    for member in page_obj.object_list:
        member_data = {
            'rank': rank,
            'username': f'{member.first_name}',
            'is_current_user': (member.pk == request.user.pk),
        }
        for k, v in ranking_field_map.items():
            member_data[k] = getattr(member, v)
        rank += 1
        members_list.append(member_data)
    
    context = {
        'group': group,
        'page_obj': page_obj,
        'members_list': members_list,
        'period': period,
        'gender': gender,
        'age': age_range_key,
        'rank_type': rank_type,
        'periods': PERIODS,
        'genders': GENDERS,
        'age_ranges': AGE_RANGES,
        'rank_types': RANK_TYPES,
        'is_group_member': is_group_member,
        'current_user_rank': current_user_rank,
        'total_participants': total_participants,
        'ranking_position': ranking_position,
        'next_url': next_url,
    }
    
    return render(request, 'strava_web/stats_ranking.html', context)

def race_ranking(request, group_id):
    if group_id == 0:
        group = None
    else:
        group = get_object_or_404(Group, pk=group_id)
    date_range = request.GET.get('date_range', 'all')
    race_distance = request.GET.get('race_distance', "FM")
    if race_distance == "":
        race_distance = "FM"
    gender = request.GET.get('gender', 'all')
    age_range = request.GET.get('age_range', 'all')
    fastest_only = request.GET.get('fastest_only') == 'yes'
    
    if fastest_only:
        queryset = Activity.objects.filter(
            is_race=True,
            chip_time__isnull=False,
            user_id=OuterRef('user_id'),
        ).select_related('user')
    else:
        queryset = Activity.objects.filter(
            is_race=True,
            chip_time__isnull=False
        ).select_related('user')
    if group:
        queryset = queryset.filter(user__groups__pk=group_id)
    now = timezone.now()
    if date_range == 'last_year':
        queryset = queryset.filter(start_date_local__gte=now - timedelta(days=365))
    elif date_range == 'last_6_months':
        queryset = queryset.filter(start_date_local__gte=now - timedelta(days=182))
    elif date_range.isdigit():
        queryset = queryset.filter(start_date_local__year=int(date_range))
    if race_distance:
        queryset = queryset.filter(race_distance=race_distance)
    if gender != 'all':
        queryset = queryset.filter(user__gender=gender)
        
    if age_range != 'all' and age_range in AGE_RANGES:
        queryset.exclude(Q(user__birth_year__isnull=True) | Q(user__birth_year=0))
        start_age, end_age = AGE_RANGES[age_range][1]
        current_year = datetime.date.today().year
        q = Q()
        if start_age is not None:
            q &= Q(user__birth_year__lte=current_year - start_age)
        if end_age is not None:
            q &= Q(user__birth_year__gte=current_year - end_age)
        queryset = queryset.filter(q)

    if fastest_only:
        fastest_times = queryset.order_by('chip_time').values('id')[:1]
        queryset = Activity.objects.filter(
            is_race=True,
            chip_time__isnull=False
        )
        queryset = queryset.annotate(
            min_id=Subquery(fastest_times)
        ).filter(
            id=F('min_id')
        )
    queryset = queryset.order_by('chip_time')
    paginator = Paginator(queryset, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 获取所有可用的年份，用于筛选器
    available_years = Activity.objects.filter(
        is_race=True,
        start_date_local__isnull=False
    ).annotate(
        year=ExtractYear('start_date_local')
    ).values_list(
        'year', flat=True
    ).distinct().order_by('-year')
    
    context = {
        'page_obj': page_obj,
        'group': group,
        'date_range': date_range,
        'race_distance': race_distance,
        'gender': gender,
        'genders': GENDERS,
        'age_range': age_range,
        'fastest_only': fastest_only,
        'age_ranges': AGE_RANGES,
        'available_years': available_years,
        'is_race_ranking_page': True,
    }
    print(date_range)
    return render(request, 'strava_web/race_ranking.html', context)

@login_required
def group_dashboard(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    is_group_admin = (group.admin == request.user)
    is_group_member = request.user.groups.filter(id=group.id).exists()
    if not group.has_dashboard:
        messages.error(request, _("This is a managment group."))
        return redirect('group_membership')

    if not (is_group_admin or is_group_member or request.user.is_superuser):
        messages.error(request, _("You do not have permission to view the group dashboard."))
        return redirect('group_membership')
    
    search_query = request.GET.get('search', '')
    gender_filter = request.GET.get('gender', 'all')
    page_number = request.GET.get('page')
    members_list = group.members.filter(is_active=True)
    if search_query:
        members_list = members_list.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query)
        )
    
    if gender_filter != 'all':
        members_list = members_list.filter(gender=gender_filter)

    # 分页
    paginator = Paginator(members_list, 10)
    page_obj = paginator.get_page(page_number)

    context = {
        'group': group,
        'page_obj': page_obj,
        'members_count': group.members.count(),
        'search_query': search_query,
        'gender': gender_filter,
        'genders': GENDERS,
    }

    return render(request, 'strava_web/group_dashboard.html', context)

