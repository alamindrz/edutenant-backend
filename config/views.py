# config/views.py
from django.shortcuts import render, redirect
from core.models import School
from django.utils import timezone
from datetime import timedelta




def home_view(request):
    """Public landing page for ALL users."""
    # Get featured schools for the public landing page
    featured_schools = School.objects.filter(
        is_active=True,
        is_featured=True,
        application_form_enabled=True
    )[:6]
    
    # Get stats for landing page
    total_schools = School.objects.filter(is_active=True).count()
    
    context = {
        'featured_schools': featured_schools,
        'total_schools': total_schools,
        'show_hero': True,
    }
    
    return render(request, 'home.html', context)  # This is your public landing

  
def school_discovery_view(request):
    """Public school discovery page."""
    from users.models import School
    from django.db.models import Q, Count
    from django.core.paginator import Paginator
    
    # Get filter parameters
    search_query = request.GET.get('q', '')
    school_type = request.GET.get('type', '')
    location = request.GET.get('location', '')
    sort = request.GET.get('sort', 'newest')
    page = request.GET.get('page', 1)
    
    # Base queryset
    schools = School.objects.filter(is_active=True, application_form_enabled=True)
    
    # Apply filters
    if search_query:
        schools = schools.filter(
            Q(name__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(address__icontains=search_query)
        )
    
    if school_type:
        schools = schools.filter(school_type=school_type)
    
    if location:
        schools = schools.filter(address__icontains=location)
    
    # Apply sorting
    if sort == 'popular':
        schools = schools.annotate(
            student_count=Count('student', distinct=True),
        ).order_by('-student_count')
    elif sort == 'name':
        schools = schools.order_by('name')
    else:  # newest
        schools = schools.order_by('-created_at')
    
    # Annotate with counts
    schools = schools.annotate(
        student_count=Count('student', distinct=True),
        staff_count=Count('staff', distinct=True),
    )
    
    # Pagination
    paginator = Paginator(schools, 12)
    schools_page = paginator.get_page(page)
    
    context = {
        'schools': schools_page,
        'search_query': search_query,
        'school_type': school_type,
        'location': location,
        'sort': sort,
        'page_title': 'Discover Schools',
    }
    
    return render(request, 'school_discovery.html', context)