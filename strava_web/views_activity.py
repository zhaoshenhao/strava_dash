from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Activity, CustomUser
from django.core.paginator import Paginator
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db.models import Q
from .forms import ActivityEditForm 

@login_required
def activities(request, user_id=None):
    if user_id:
        target_user = get_object_or_404(CustomUser, id=user_id)
    else:
        target_user = request.user
    user_activities = Activity.objects.filter(user=target_user)
    current_path = request.path
    is_race_page = 'races' in current_path
    page_user_id = target_user.id

    # 1. Date Filters (Year, Month, Week)
    selected_year = request.GET.get('year')
    selected_month = request.GET.get('month')
    selected_week = request.GET.get('week')
    search_query = request.GET.get('search-input', '')

    if selected_year:
        user_activities = user_activities.filter(start_date_local__year=selected_year)
    if selected_month:
        user_activities = user_activities.filter(start_date_local__month=selected_month)
    if selected_week:
        user_activities = user_activities.filter(start_date_local__week=selected_week)
    if search_query:
        user_activities = user_activities.filter(Q(name__icontains=search_query))

    available_years = Activity.objects.filter(user=target_user) \
                                   .values_list('start_date_local__year', flat=True) \
                                   .distinct().order_by('-start_date_local__year')
    available_months = [
        ('1', _('January')), ('2', _('February')), ('3', _('March')), ('4', _('April')),
        ('5', _('May')), ('6', _('June')), ('7', _('July')), ('8', _('August')),
        ('9', _('September')), ('10', _('October')), ('11', _('November')), ('12', _('December')),
    ]
    available_weeks = list(range(1, 53)) # Weeks 1-52

    # 2. Distance Filters (using values in meters as per Activity model) - 已恢复为你原始代码的逻辑
    selected_distance = request.GET.get('distance')
    # Define distance thresholds in METERS
    DIST_5K = 5000 # 5 km
    DIST_10K = 10000 # 10 km
    DIST_15K = 15000 # 15 km
    DIST_20K = 20000 # 20 km
    DIST_25K = 25000 # 25 km
    DIST_30K = 30000 # 30 km
    DIST_35K = 35000 # 35 km
    DIST_40K = 40000 # 40 km
    DIST_45K = 45000 # 45 km
    DIST_50K = 50000 # 50 km
    DIST_100K = 100000 # 100 km

    if selected_distance:
        if selected_distance == '0-5k':
            user_activities = user_activities.filter(distance__gte=0, distance__lt=DIST_5K)
        elif selected_distance == '5-10k':
            user_activities = user_activities.filter(distance__gte=DIST_5K, distance__lt=DIST_10K)
        elif selected_distance == '10-15k':
            user_activities = user_activities.filter(distance__gte=DIST_10K, distance__lt=DIST_15K)
        elif selected_distance == '15-20k':
            user_activities = user_activities.filter(distance__gte=DIST_15K, distance__lt=DIST_20K)
        elif selected_distance == '20-25k':
            user_activities = user_activities.filter(distance__gte=DIST_20K, distance__lt=DIST_25K)
        elif selected_distance == '25-30k':
            user_activities = user_activities.filter(distance__gte=DIST_25K, distance__lt=DIST_30K)
        elif selected_distance == '30-35k':
            user_activities = user_activities.filter(distance__gte=DIST_30K, distance__lt=DIST_35K)
        elif selected_distance == '35-40k':
            user_activities = user_activities.filter(distance__gte=DIST_35K, distance__lt=DIST_40K)
        elif selected_distance == '40-45k':
            user_activities = user_activities.filter(distance__gte=DIST_40K, distance__lt=DIST_45K)
        elif selected_distance == '45-50k':
            user_activities = user_activities.filter(distance__gte=DIST_45K, distance__lt=DIST_50K)
        elif selected_distance == '50-100k':
            user_activities = user_activities.filter(distance__gte=DIST_50K, distance__lt=DIST_100K)
        elif selected_distance == '100k_plus':
            user_activities = user_activities.filter(distance__gte=DIST_100K)

    # 3. Is Race Filter
    is_race_filter = request.GET.get('is_race_filter')
    if is_race_page:
        user_activities = user_activities.filter(is_race=True)
    elif is_race_filter:
        if is_race_filter == 'yes':
            user_activities = user_activities.filter(is_race=True)
        elif is_race_filter == 'no':
            user_activities = user_activities.filter(is_race=False)


    selected_sort_by = request.GET.get('sort_by', 'start_date_local') # 默认按日期排序
    selected_order = request.GET.get('order', 'desc') # 默认降序

    if selected_order == 'desc':
        user_activities = user_activities.order_by(f'-{selected_sort_by}')
    else:
        user_activities = user_activities.order_by(selected_sort_by)

    # --- Pagination Logic ---
    paginator = Paginator(user_activities, 10)  # 每页显示 10 条活动
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    sortable_fields = [
        ('start_date_local', _('Date')),
        ('name', _('Activity Name')),
        ('distance', _('Distance (km)') if request.user.use_metric else _('Distance (mile)')),
        ('chip_time' if is_race_page else 'elapsed_time', _('Chip Time') if is_race_page else _('Elapsed Time')),
        ('elevation_gain', _('Elevation Gain (m)') if request.user.use_metric else _('Elevation Gain (feet)')),
        ('average_speed', _('Avg. Pace (min/km)') if request.user.use_metric else _('Avg. Pace (min/mile)')),
        ('average_heartrate', _('Avg. HR')),
        ('average_cadence', _('Ave. Cadence')),
    ]
    if is_race_page:
        sortable_fields.insert(3, 
            ('race_distance', _('Race Distance'))
        )
    else:
        sortable_fields.append(('is_race',_('Is Race')))
        

    context = {
        'page_obj': page_obj,
        'available_years': available_years,
        'available_months': available_months,
        'available_weeks': available_weeks,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'selected_week': selected_week,
        'selected_distance': selected_distance,
        'is_race_filter': is_race_filter,
        'selected_sort_by': selected_sort_by,
        'selected_order': selected_order,
        'sortable_fields': sortable_fields,
        'search_query': search_query,
        'use_metric': request.user.use_metric,
        'user_id': page_user_id,
        'is_race_page': is_race_page,
    }
    return render(request, 'strava_web/activities.html', context)

@login_required
@require_POST # 只允许 POST 请求
def update_activity_ajax(request, activity_id):
    activity = get_object_or_404(Activity, id=activity_id, user=request.user)
    form = ActivityEditForm(request.POST, instance=activity)

    if form.is_valid():
        # 处理 chip_time 逻辑：如果 is_race 为 True 且 chip_time 为空或 0，则使用 elapsed_time
        if form.cleaned_data['is_race'] and (form.cleaned_data['chip_time'] is None or form.cleaned_data['chip_time'] == 0):
            form.instance.chip_time = activity.elapsed_time # 使用原始活动的 elapsed_time
        activity = form.save() # 保存到数据库

        # 返回更新后的数据，用于前端刷新行
        return JsonResponse({
            'success': True,
            'message': _("Activity updated successfully!"),
            'activity_data': {
                'id': activity.id,
                'name': activity.name,
                'distance': activity.distance,
                'elapsed_time': activity.elapsed_time,
                'is_race': activity.is_race,
                'chip_time': activity.chip_time,
                'race_distance': activity.race_distance,
                'race_distance_display': activity.get_race_distance_display(),
                'strava_id': activity.strava_id,
                'start_date_local': activity.start_date_local,
                'strava_url': f"https://www.strava.com/activities/{activity.strava_id}"
            }
        })
    else:
        # 返回表单错误
        errors = form.errors.as_json()
        return JsonResponse({'success': False, 'errors': errors}, status=400)