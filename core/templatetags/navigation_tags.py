# core/templatetags/navigation_tags.py
from django import template

register = template.Library()

@register.filter
def is_visible(item, user_context):
    """Check if navigation item should be visible."""
    if hasattr(item, 'is_visible'):
        return item.is_visible(*user_context)
    return True

@register.filter
def get_url(item):
    """Get URL for navigation item."""
    if hasattr(item, 'get_url'):
        return item.get_url()
    return '#'

@register.filter
def has_badge(item):
    """Check if item has badge."""
    return hasattr(item, 'badge_count') and item.badge_count > 0