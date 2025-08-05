from datetime import timedelta
from django.utils import timezone
from django.urls import reverse

def get_float(val):
    return val if val else 0.0

def get_int(val):
    return val if val else 0

def get_monday_of_week(given_date):
    days_since_monday = given_date.weekday() % 7
    monday_datetime = given_date - timedelta(days=days_since_monday)
    return monday_datetime.replace(hour=0, minute=0, second=0, microsecond=0)

def get_days_ago(given_date, days):
    start_date = given_date - timedelta(days=days)
    return start_date.replace(hour=0, minute=0, second=0, microsecond=0)

def calculate_pace(total_distance_meters, total_time_seconds, is_metric):
    if total_distance_meters <= 0 or total_time_seconds < 0:
        return "N/A"
    if total_time_seconds == 0:
        return "0:00"
    if is_metric:
        unit_distance_meters = 1000  # 1公里 = 1000米
    else:
        unit_distance_meters = 1609.34  # 1英里 = 1609.34米
    pace_seconds_per_unit = (total_time_seconds / total_distance_meters) * unit_distance_meters
    return second_to_pace(pace_seconds_per_unit)

def second_to_pace(seconds):
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"

def speed_pace(speed, is_metric):
    if is_metric:
        unit_distance_meters = 1000  # 1公里 = 1000米
    else:
        unit_distance_meters = 1609.34  # 1英里 = 1609.34米
    pace_seconds_per_unit = unit_distance_meters / speed
    return second_to_pace(pace_seconds_per_unit)

def convert_seconds_to_dhms(total_seconds):
    if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
        # Handle non-integer, non-positive, or non-numeric input
        return 0, 0, 0, 0

    total_seconds = int(total_seconds) # Ensure it's an integer for calculations

    days = total_seconds // (24 * 3600)
    remaining_seconds_after_days = total_seconds % (24 * 3600)

    hours = remaining_seconds_after_days // 3600
    remaining_seconds_after_hours = remaining_seconds_after_days % 3600

    minutes = remaining_seconds_after_hours // 60
    seconds = remaining_seconds_after_hours % 60
    return days, hours, minutes, seconds

def local_now():
    utc_now = timezone.now()
    return timezone.localtime(utc_now)

def get_next_url(request, def_next):
    next_url = request.POST.get('next')
    if not next_url:
        next_url = request.GET.get('next')
    if not next_url:
        next_url = reverse(def_next)
    return next_url
