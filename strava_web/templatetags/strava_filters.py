# strava_web/templatetags/strava_filters.py

from django import template

register = template.Library()

@register.filter
def div(value, arg):
    """
    Divides the value by the argument.
    Usage: {{ value|div_filter:arg }}
    """
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return None # or handle error as appropriate

@register.filter
def duration(value, withDay):
    d1, h1, m1, s1 = convert_seconds_to_dhms(value)
    if withDay == 1:
        return f"{d1}d {h1}:{m1}:{s1}"
    else:
        h1 = d1 * 24 + h1
        return f"{h1}:{m1}:{s1}"
        
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

