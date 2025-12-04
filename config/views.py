# config/views.py - UPDATED
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.core.paginator import Paginator

from users.models import School
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count



def home_view(request):
    """Home page with role-based redirection"""
    if request.user.is_authenticated:
        # Get user's current school context
        current_school = getattr(request, 'school', None)
        
        if current_school:
            # User has active school context - redirect to appropriate dashboard
            profile = request.user.profile_set.filter(school=current_school).first()
            if profile and profile.role:
                if profile.role.system_role_type in ['principal', 'admin']:
                    return redirect('users:dashboard')
                elif profile.role.system_role_type == 'teacher':
                    return redirect('attendance:dashboard')
                elif profile.role.system_role_type == 'parent':
                    return redirect('students:parent_dashboard')
            
            # Fallback to general dashboard
            return redirect('users:dashboard')
        else:
            # User has no active school context - show school management
            return redirect('users:school_selection')
    
    # Non-authenticated users see landing page
    context = {
        'total_schools': School.objects.filter(is_active=True).count(),
        'active_today': School.objects.filter(
            is_active=True,
            updated_at__date=timezone.now().date()
        ).count(),
        'new_this_week': School.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=7)
        ).count(),
    }
    return render(request, 'home.html', context)

def school_discovery_view(request):
    """School discovery for ALL users - teachers can explore opportunities"""
    if not request.user.is_authenticated:
        return redirect('account_login')
    
    # Get filter parameters
    search_query = request.GET.get('q', '')
    school_type = request.GET.get('type', '')
    location = request.GET.get('location', '')
    sort = request.GET.get('sort', 'newest')
    page = request.GET.get('page', 1)
    
    # Base queryset - show schools with open positions prominently
    schools = School.objects.filter(is_active=True)
    
    # Apply filters (same as before)
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
            staff_count=Count('staff', distinct=True)
        ).order_by('-student_count', '-staff_count')
    elif sort == 'hiring':
        # Show schools with open positions first
        schools = schools.annotate(
            open_positions=Count('staff', filter=Q(staff__is_active=False) & Q(staff__position__icontains='teacher'))
        ).order_by('-open_positions', '-created_at')
    elif sort == 'name':
        schools = schools.order_by('name')
    else:  # newest
        schools = schools.order_by('-created_at')
    
    # Annotate with counts
    schools = schools.annotate(
        student_count=Count('student', distinct=True),
        staff_count=Count('staff', distinct=True),
        user_school_count=Count('profile', filter=Q(profile__user=request.user))
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
        'page_title': 'Discover Schools - Teaching Opportunities',
        'user_has_schools': request.user.profile_set.exists(),
    }
    
    return render(request, 'school_discovery.html', context)