# strava_web/templatetags/strava_filters.py
from django import template
from strava_web.utils import convert_seconds_to_dhms, calculate_pace, speed_pace

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
    if value <= 0:
        if withDay == 1:
            return "- --:--:--"
        elif withDay == 2:
            return "--:--"
        else:
            return  "--:--:--"
    d1, h1, m1, s1 = convert_seconds_to_dhms(value)
    if withDay == 1:
        return f"{d1}d {h1:02d}:{m1:02d}:{s1:02d}"
    elif withDay == 2:
        return f"{m1:02d}:{s1:02d}"
    else:
        h1 = d1 * 24 + h1
        return f"{h1:02d}:{m1:02d}:{s1:02d}"
        
@register.filter
def km_pace(distance, time):
    return calculate_pace(distance, time, True)

@register.filter
def mile_pace(distance, time):
    return calculate_pace(distance, time, False)

@register.filter
def speed_km_pace(speed):
    return speed_pace(speed, True)

@register.filter
def speed_mile_pace(speed):
    return speed_pace(speed, False)

@register.filter
def format_number(number, decimal_places=2):
    if isinstance(number, int):
        return f"{number:,}"
    elif isinstance(number, float):
        format_spec = f",.{decimal_places}f"
        return f"{number:{format_spec}}"
    else:
        return number