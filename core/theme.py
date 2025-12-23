# core/theme.py - NEW FILE
import json
from django.conf import settings

class ThemeManager:
    """Manages theme switching and dark mode support."""
    
    THEMES = {
        'light': {
            'primary': '#0d6efd',
            'secondary': '#6c757d',
            'success': '#198754',
            'danger': '#dc3545',
            'warning': '#ffc107',
            'info': '#0dcaf0',
            'body-bg': '#ffffff',
            'body-color': '#212529',
            'border-color': '#dee2e6',
        },
        'dark': {
            'primary': '#0d6efd',
            'secondary': '#6c757d',
            'success': '#198754',
            'danger': '#dc3545',
            'warning': '#ffc107',
            'info': '#0dcaf0',
            'body-bg': '#212529',
            'body-color': '#f8f9fa',
            'border-color': '#495057',
        },
    }
    
    @staticmethod
    def get_theme(request):
        """Get current theme from session or default."""
        # Check localStorage via cookie
        theme_cookie = request.COOKIES.get('theme')
        if theme_cookie:
            return theme_cookie
        
        # Check session
        theme_session = request.session.get('theme')
        if theme_session:
            return theme_session
        
        # Default to light
        return 'light'
    
    @staticmethod
    def set_theme(request, theme):
        """Set theme in session."""
        if theme in ['light', 'dark']:
            request.session['theme'] = theme
            request.session.modified = True
    
    @staticmethod
    def get_theme_css(theme):
        """Generate CSS variables for the theme."""
        colors = ThemeManager.THEMES.get(theme, ThemeManager.THEMES['light'])
        
        css = f"""
        :root {{
            --bs-primary: {colors['primary']};
            --bs-secondary: {colors['secondary']};
            --bs-success: {colors['success']};
            --bs-danger: {colors['danger']};
            --bs-warning: {colors['warning']};
            --bs-info: {colors['info']};
            --bs-body-bg: {colors['body-bg']};
            --bs-body-color: {colors['body-color']};
            --bs-border-color: {colors['border-color']};
        }}
        """
        
        return css

# core/context_processors.py - UPDATED
from core.theme import ThemeManager

def theme_context(request):
    """Add theme context to all templates."""
    theme = ThemeManager.get_theme(request)
    
    return {
        'current_theme': theme,
        'theme_css': ThemeManager.get_theme_css(theme),
        'is_dark_mode': theme == 'dark',
    } 