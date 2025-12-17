# users/templatetags/application_filters.py
from django import template

register = template.Library()

@register.filter
def filter_status(queryset, status):
    """Filter applications by status."""
    if hasattr(queryset, 'filter'):
        return queryset.filter(status=status)
    return [app for app in queryset if app.status == status]

@register.filter
def dict_values(dictionary):
    """Get dictionary values."""
    return dictionary.values() if dictionary else []