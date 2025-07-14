# strava_web/templatetags/strava_filters.py
from django import template
from strava_web.utils import convert_seconds_to_dhms, calculate_pace

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
        
@register.filter
def km_pace(distance, time):
    return calculate_pace(distance, time, True)

@register.filter
def mile_pace(distance, time):
    return calculate_pace(distance, time, False)
