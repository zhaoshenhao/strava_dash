from django import template
from strava_web.utils import convert_seconds_to_dhms, calculate_pace, speed_pace
from django.utils.translation import gettext_lazy as _

register = template.Library()

@register.simple_tag(takes_context=True)
def url_param_replace(context, **kwargs):
    d = context['request'].GET.copy()
    for k, v in kwargs.items():
        d[k] = v
    for k in [key for key, v_list in d.lists() if not v_list]:
        del d[k]
    return d.urlencode()

@register.filter
def div(value, arg):
    """
    Divides the value by the argument.
    Usage: {{ value|div_filter:arg }}
    """
    try:
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return None

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

@register.filter
def gender(gender):
    if not gender:
        return '-'
    if gender.upper() == 'M':
        return _('Male')
    if gender.upper() == 'F':
        return _('Female')
    return '-'

@register.filter
def app_status(val):
    if val == 'pending':
        return _('Pending')
    if val == 'approved':
        return _('Approved')
    if val == 'rejected':
        return _('Rejected')
    return '-'
