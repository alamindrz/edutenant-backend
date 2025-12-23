# core/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Get a value from a dictionary by key.
    Usage: {{ my_dict|get_item:key }}
    """
    if dictionary and isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def subtract(value, arg):
    """
    Subtract arg from value.
    Usage: {{ value|subtract:arg }}
    """
    try:
        return int(value) - int(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def divisible(value, arg):
    """
    Divide value by arg.
    Usage: {{ value|divisible:arg }}
    """
    try:
        if float(arg) == 0:
            return 0
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def multiply(value, arg):
    """
    Multiply value by arg.
    Usage: {{ value|multiply:arg }}
    """
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return value

@register.filter
def get_range(value):
    """
    Create a range from 0 to value-1.
    Usage: {% for i in 5|get_range %}
    """
    return range(value)

@register.filter
def join_list(value, separator=", "):
    """
    Join a list with a separator.
    Usage: {{ my_list|join_list:", " }}
    """
    if isinstance(value, list):
        return separator.join(str(item) for item in value)
    return value

@register.filter
def format_phone(value):
    """
    Format phone number for display.
    Usage: {{ phone_number|format_phone }}
    """
    if not value:
        return ""
    
    # Remove all non-digit characters
    cleaned = ''.join(filter(str.isdigit, str(value)))
    
    # Format Nigerian phone numbers
    if len(cleaned) == 11 and cleaned.startswith('0'):
        return f"+234 {cleaned[1:4]} {cleaned[4:7]} {cleaned[7:]}"
    elif len(cleaned) == 10 and cleaned.startswith('0'):
        return f"+234 {cleaned[1:4]} {cleaned[4:7]} {cleaned[7:]}"
    
    return value

@register.filter
def truncate_words(value, arg):
    """
    Truncate a string after a certain number of words.
    Usage: {{ text|truncate_words:10 }}
    """
    try:
        words = value.split()
        if len(words) <= int(arg):
            return value
        return ' '.join(words[:int(arg)]) + '...'
    except (AttributeError, ValueError):
        return value

@register.filter
def percentage(value, arg=100):
    """
    Format a decimal as percentage.
    Usage: {{ 0.85|percentage }} or {{ value|percentage:100 }}
    """
    try:
        return f"{float(value) * 100:.1f}%"
    except (ValueError, TypeError):
        return "0%" 