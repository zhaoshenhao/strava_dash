# strava_web/services.py
import requests
from datetime import timedelta, timezone
from django.conf import settings
from django.utils.timezone import now
from django.db import transaction
from django.contrib.auth import get_user_model
from strava_web.models import Activity
from strava_web.utils import get_monday_of_week, get_float, get_int, get_days_ago, local_now

User = get_user_model() # 在服务层获取用户模型

def refresh_strava_token(user_instance):
    """
    使用 refresh_token 获取新的 access_token 和 refresh_token。
    """
    if not user_instance.strava_refresh_token:
        raise ValueError("No refresh token available for this user.")

    payload = {
        'client_id': settings.STRAVA_CLIENT_ID,
        'client_secret': settings.STRAVA_CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': user_instance.strava_refresh_token
    }

    try:
        response = requests.post(settings.STRAVA_TOKEN_URL, data=payload)
        response.raise_for_status()
        token_data = response.json()

        # 更新用户模型中的令牌信息
        # 使用原子性操作确保数据一致性
        with transaction.atomic():
            user_instance.strava_access_token = token_data['access_token']
            user_instance.strava_refresh_token = token_data['refresh_token']
            user_instance.strava_token_expires_at = now() + timedelta(seconds=token_data['expires_in'])
            user_instance.save(update_fields=['strava_access_token', 'strava_refresh_token', 'strava_token_expires_at'])

        return {
            'access_token': token_data['access_token'],
            'refresh_token': token_data['refresh_token'],
            'expires_in': token_data['expires_in']
        }
    except requests.exceptions.RequestException as e:
        raise Exception(f"Failed to refresh Strava token: {e}")

def guess_race_distance(distance_meters):
    if 800 <= distance_meters <= 1000:
        return "1km"
    elif 4700 <= distance_meters <= 5300:
        return "5km"
    elif 9600 <= distance_meters <= 10400:
        return "10km"
    elif 14500 <= distance_meters <= 15500:
        return "15km"
    elif 15500 <= distance_meters <= 16500:
        return "10mi"
    elif 20600 <= distance_meters <= 21600:
        return "HM"
    elif 29500 <= distance_meters <= 30500:
        return "30km"
    elif 41800 <= distance_meters <= 42900:
        return "FM"
    elif 49000 <= distance_meters <= 51000:
        return "50km"
    elif 98000 <= distance_meters <= 102000:
        return "100km"
    elif 147000 <= distance_meters <= 153000:
        return "150km"
    elif 156000 <= distance_meters <= 164900:
        return "100mi"
    else:
        return "Other" # Or handle other cases as needed

#@transaction.atomic # 确保数据同步的原子性
def sync_strava_data_for_user(user_instance, days, stdout):
    """
    获取用户的 Strava 数据（统计和跑步比赛活动）。
    """
    access_token = user_instance.get_strava_access_token() # 使用用户模型的方法获取 token
    if not access_token:
        raise ValueError("Cannot get Strava access token for this user. Re-authorization may be needed.")

    headers = {'Authorization': f'Bearer {access_token}'}

    # 1. 获取聚合统计数据
    stdout.write(f"Last Sync of user ({user_instance.username}): {user_instance.last_strava_sync}")
    try:
        stdout.write(f"Get user stats from Strava")
        stats_url = f"{settings.STRAVA_API_BASE_URL}/athletes/{user_instance.strava_id}/stats"
        stats_response = requests.get(stats_url, headers=headers)
        stats_response.raise_for_status()
        stats_data = stats_response.json()

        # 将 stats_data 映射到 user_instance 的统计字段并保存
        user_instance.recent_run_distance = get_float(stats_data['recent_run_totals']['distance'])
        user_instance.recent_run_count = get_int(stats_data['recent_run_totals']['count'])
        user_instance.recent_run_moving_time = get_int(stats_data['recent_run_totals']['moving_time'])
        user_instance.recent_run_elapsed_time = get_int(stats_data['recent_run_totals']['elapsed_time'])
        user_instance.recent_run_elevation_gain = get_int(stats_data['recent_run_totals']['elevation_gain'])

        user_instance.ytd_run_distance = get_float(stats_data['ytd_run_totals']['distance'])
        user_instance.ytd_run_count = get_int(stats_data['ytd_run_totals']['count'])
        user_instance.ytd_run_moving_time = get_int(stats_data['ytd_run_totals']['moving_time'])
        user_instance.ytd_run_elapsed_time = get_int(stats_data['ytd_run_totals']['elapsed_time'])
        user_instance.ytd_run_elevation_gain = get_int(stats_data['ytd_run_totals']['elevation_gain'])

        user_instance.all_time_run_distance = get_float(stats_data['all_run_totals']['distance'])
        user_instance.all_time_run_count = get_int(stats_data['all_run_totals']['count'])
        user_instance.all_time_run_moving_time = get_int(stats_data['all_run_totals']['moving_time'])
        user_instance.all_time_run_elapsed_time = get_int(stats_data['all_run_totals']['elapsed_time'])
        user_instance.all_time_run_elevation_gain = get_int(stats_data['all_run_totals']['elevation_gain'])
        user_instance.save(update_fields=[
            'recent_run_distance', 'recent_run_count', 'recent_run_moving_time', 'recent_run_elapsed_time', 'recent_run_elevation_gain',
            'ytd_run_distance', 'ytd_run_count', 'ytd_run_moving_time', 'ytd_run_elapsed_time', 'ytd_run_elevation_gain',
            'all_time_run_distance', 'all_time_run_count', 'all_time_run_moving_time', 'all_time_run_elapsed_time', 'all_time_run_elevation_gain',
        ])
        stdout.write(f"Save user stats. Recent run counts: {user_instance.recent_run_count}")
    except requests.exceptions.RequestException as e:
        stdout.write(f"Failed to get Strava stats for user {user_instance.id}: {e}")
        # 这里可以选择记录错误，或者抛出异常让调用者处理

    # 2. 获取跑步比赛活动数据 (增量更新)
    params = {'per_page': 200, 'type': 'Run'} # 默认只获取 Run 类型活动
    if user_instance.last_strava_sync:
        # 将 datetime 对象转换为 Unix timestamp (秒)
        if days:
            utc_last_sync = now() - timedelta(days=days)
        else:
            utc_last_sync = user_instance.last_strava_sync.astimezone(timezone.utc)
        params['after'] = int(utc_last_sync.timestamp())

    page = 1
    has_more_activities = True
    has_change = False

    while has_more_activities:
        params['page'] = page
        try:
            activities_url = f"{settings.STRAVA_API_BASE_URL}/athlete/activities"
            activities_response = requests.get(activities_url, headers=headers, params=params)
            activities_response.raise_for_status()
            activities_data = activities_response.json()

            if not activities_data:
                has_more_activities = False
                break

            for activity_summary in activities_data:
                if activity_summary.get('type') == 'Run':
                    has_change = True
                    is_race = (activity_summary.get('workout_type') == 1)
                    chip_time = activity_summary.get('moving_time', 0) if is_race else 0
                    race_distance = guess_race_distance(activity_summary.get('distance', 0)) if is_race else None
                    
                    Activity.objects.update_or_create(
                        user=user_instance,
                        strava_id=activity_summary.get('id'),
                        defaults={
                            'name': activity_summary.get('name', ''),
                            'activity_type': activity_summary.get('type', 'Run'),
                            'workout_type': activity_summary.get('workout_type') if activity_summary.get('workout_type') else 0,
                            'distance': activity_summary.get('distance', 0),
                            'moving_time': activity_summary.get('moving_time', 0),
                            'elapsed_time': activity_summary.get('elapsed_time', 0),
                            'chip_time': chip_time,
                            'race_distance': race_distance,
                            'elevation_gain': activity_summary.get('total_elevation_gain', 0),
                            'start_date': activity_summary.get('start_date'),
                            'start_date_local': activity_summary.get('start_date_local'),
                            'timezone': activity_summary.get('timezone'),
                            'average_speed': activity_summary.get('average_speed'),
                            'max_speed': activity_summary.get('max_speed'),
                            'average_heartrate': activity_summary.get('average_heartrate'),
                            'max_heartrate': activity_summary.get('max_heartrate'),
                            'average_cadence': activity_summary.get('average_cadence'),
                            'has_heartrate': activity_summary.get('has_heartrate', False),
                            'has_power': activity_summary.get('has_power', False),
                            'is_race': is_race, 
                        }
                    )
                    stdout.write(f"Processed run activity: {activity_summary.get('start_date')} (ID: {activity_summary['id']})")
            page += 1
            if len(activities_data) < params['per_page']:
                has_more_activities = False
        except requests.exceptions.RequestException as e:
            stdout.write(f"Failed to get Strava activities for user {user_instance.id} (page {page}): {e}")
            has_more_activities = False # 遇到错误停止分页
        except Exception as e:
            stdout.write(f"Error processing activity data for user {user_instance.id}: {e}")
            has_more_activities = False

    # 遍历所有获取到的跑步活动，计算本周数据
    if has_change:
        update_stats(user_instance, stdout)

    # 更新最后同步时间
    user_instance.last_strava_sync = now()
    user_instance.save(update_fields=['last_strava_sync'])
    stdout.write(f"Strava data sync completed for user {user_instance.id}.")
    
def get_weekly_activities(user_instance):
    start_of_28_days = get_days_ago(local_now(), 28)
    activities = Activity.objects.filter(
        activity_type='Run',
        start_date_local__gte=start_of_28_days,
        user=user_instance,
    ).order_by('start_date_local')
    return activities
    
def update_stats(user_instance, stdout):
    all_recent_activities = get_weekly_activities(user_instance)
    start_of_week_local = get_monday_of_week(local_now())
    if not all_recent_activities:
        stdout.write(f"Weekly stats for user {user_instance.id} are up-to-date. No save needed.")
        return
    weekly_distance = 0.0
    weekly_count = 0
    weekly_moving_time = 0
    weekly_moving_time1 = 0
    weekly_elapsed_time = 0
    weekly_elevation_gain = 0
    weekly_time_hr = 0.0
    weekly_max_heartrate_val = 0.0
    recent_time_hr = 0.0
    recent_moving_time1 = 0.0
    recent_max_heartrate_val = 0.0
    for activity in all_recent_activities:
        if activity.has_heartrate and activity.average_heartrate is not None:
            time_hr = activity.moving_time * activity.average_heartrate
        else:
            time_hr = None
        if time_hr:
            recent_moving_time1 += activity.moving_time
            recent_time_hr += time_hr
        if activity.max_heartrate is not None:
            recent_max_heartrate_val = max(recent_max_heartrate_val, activity.max_heartrate)
        if activity.start_date_local >= start_of_week_local:
            weekly_distance += activity.distance
            weekly_count += 1
            weekly_moving_time += activity.moving_time
            weekly_elapsed_time += activity.elapsed_time
            weekly_elevation_gain += activity.elevation_gain
            if time_hr:
                weekly_moving_time1 += activity.moving_time
                weekly_time_hr += time_hr
            if activity.max_heartrate is not None:
                weekly_max_heartrate_val = max(weekly_max_heartrate_val, activity.max_heartrate)
    # 仅当计算出的周数据与现有数据不同时才保存，减少不必要的数据库写入
    update_fields_for_weekly = []
    update_fields_for_weekly.append('weekly_run_distance')
    update_fields_for_weekly.append('weekly_run_count')
    update_fields_for_weekly.append('weekly_run_moving_time')
    update_fields_for_weekly.append('weekly_run_elapsed_time')
    update_fields_for_weekly.append('weekly_run_elevation_gain')
    update_fields_for_weekly.append('recent_max_heartrate')
    update_fields_for_weekly.append('recent_avg_heartrate')
    update_fields_for_weekly.append('weekly_max_heartrate')
    update_fields_for_weekly.append('weekly_avg_heartrate')
    user_instance.recent_max_heartrate = recent_max_heartrate_val
    user_instance.recent_avg_heartrate = recent_time_hr / recent_moving_time1 if recent_moving_time1 else 0
    user_instance.weekly_run_distance = weekly_distance
    user_instance.weekly_run_count = weekly_count
    user_instance.weekly_run_moving_time = weekly_moving_time
    user_instance.weekly_run_elapsed_time = weekly_elapsed_time
    user_instance.weekly_run_elevation_gain = weekly_elevation_gain
    user_instance.weekly_max_heartrate = weekly_max_heartrate_val
    user_instance.weekly_avg_heartrate = weekly_time_hr / weekly_moving_time1 if weekly_moving_time1 else 0
    user_instance.save(update_fields=update_fields_for_weekly)
    stdout.write(f"Weekly stats updated for user {user_instance.id}.")

