# config/context_processors.py
from users.models import Profile, TeacherApplication
from admissions.models import Application


def navigation_permissions(request):
    """Add role-based permissions for navigation"""
    context = {}
    
    if request.user.is_authenticated and hasattr(request, 'school'):
        try:
            profile = request.user.profile_set.get(school=request.school)
            role = profile.role
            
            # Permission flags
            context.update({
                # Admissions management (Principal/Admin only)
                'user_can_manage_admissions': (
                    role and (
                        role.system_role_type in ['principal', 'admin'] or
                        role.can_manage_students or
                        'manage_admissions' in getattr(role, 'permissions', [])
                    )
                ),
                
                # Staff management (Principal/Admin only)
                'user_can_manage_staff': (
                    role and (
                        role.system_role_type in ['principal', 'admin'] or
                        role.can_manage_staff
                    )
                ),
                
                # Attendance (Teachers & Admin)
                'user_can_manage_attendance': (
                    role and (
                        role.system_role_type in ['principal', 'admin', 'teacher'] or
                        'manage_attendance' in getattr(role, 'permissions', [])
                    )
                ),
                
                # Student viewing (Teachers, Parents, Admin)
                'user_can_view_students': (
                    role and (
                        role.system_role_type in ['principal', 'admin', 'teacher', 'parent'] or
                        role.can_manage_students
                    )
                ),
                
                # Academic management (Teachers & Admin)
                'user_can_manage_academics': (
                    role and (
                        role.system_role_type in ['principal', 'admin', 'teacher'] or
                        role.can_manage_academics
                    )
                ),
                
                # Counts with permission checks
                'admission_pending_count': (
                    Application.objects.filter(form__school=request.school, status='submitted').count()
                    if role and role.system_role_type in ['principal', 'admin'] else 0
                ),
                
                'pending_applications_count': (
                    TeacherApplication.objects.filter(school=request.school, status='pending').count()
                    if role and role.system_role_type in ['principal', 'admin'] else 0
                ),
                
                'my_pending_applications': (
                    TeacherApplication.objects.filter(applicant=request.user, status='pending').count()
                    if not (role and role.system_role_type in ['principal', 'admin']) else 0
                ),
            })
            
        except Profile.DoesNotExist:
            pass
    
    return context