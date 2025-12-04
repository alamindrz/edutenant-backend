# core/views.py - ADD THIS
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["POST"])
def toggle_theme_view(request):
    """Toggle between light and dark theme with HTMX support."""
    current_theme = request.session.get('theme', 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    request.session['theme'] = new_theme
    request.session.modified = True
    
    return JsonResponse({
        'theme': new_theme,
        'message': f'Switched to {new_theme} mode'
    })