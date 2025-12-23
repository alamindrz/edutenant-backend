# core/templatetags/navigation_tags.py - UPDATED
from django import template
from django.conf import settings

register = template.Library()

# === ADD THIS SIMPLE TAG ===
@register.simple_tag
def get_navigation_items(context='default'):
    """Return navigation items based on context.
    
    Args:
        context: 'default', 'mobile_bottom', etc.
    
    Returns:
        List of navigation items with name, url, icon, active, etc.
    """
    
    # Default public navigation items
    if context == 'mobile_bottom':
        return [
            {
                'name': 'Home',
                'url': '/',
                'icon': 'bi-house',
                'active': False,
                'badge_count': 0
            },
            {
                'name': 'Schools',
                'url': '/schools/',
                'icon': 'bi-building',
                'active': False,
                'badge_count': 0
            },
            {
                'name': 'Apply',
                'url': '/apply/',
                'icon': 'bi-pencil',
                'active': False,
                'badge_count': 0
            },
            {
                'name': 'Profile',
                'url': '/login/',
                'icon': 'bi-person',
                'active': False,
                'badge_count': 0
            },
        ]
    else:
        # Default desktop navigation
        return [
            {
                'name': 'Home',
                'url': '/',
                'active': True,
                'badge_count': 0
            },
            {
                'name': 'Schools',
                'url': '/schools/',
                'active': False,
                'badge_count': 0
            },
            {
                'name': 'Apply',
                'url': '/apply/',
                'active': False,
                'badge_count': 0
            },
            {
                'name': 'About',
                'url': '/about/',
                'active': False,
                'badge_count': 0
            },
            {
                'name': 'Contact',
                'url': '/contact/',
                'active': False,
                'badge_count': 0
            },
            {
                'name': 'Login',
                'url': '/login/',
                'active': False,
                'badge_count': 0
            },
        ]


# === EXISTING FILTERS (keep these) ===
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