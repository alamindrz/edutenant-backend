# users/admin.py 
"""
CLEANED USER ADMIN - Using shared architecture
NO circular imports, consistent field naming
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from django.apps import apps

# SHARED IMPORTS
from shared.constants import PARENT_PHONE_FIELD

# LOCAL IMPORTS ONLY (User model is safe)
from .models import User

# Helper for lazy model loading
def _get_model(model_name, app_label='users'):
    """Get model lazily to avoid circular imports."""
    return apps.get_model(app_label, model_name)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Custom admin for User model with shared field naming."""
    list_display = ('email', 'first_name', 'last_name', 'current_school', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'is_superuser', 'current_school')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', PARENT_PHONE_FIELD)}),  # ✅ Use shared constant
        (_('School Context'), {'fields': ('current_school',)}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name', PARENT_PHONE_FIELD, 'is_staff', 'is_active')}  # ✅ Use shared constant
        ),
    )
    search_fields = ('email', 'first_name', 'last_name', PARENT_PHONE_FIELD)  # ✅ Use shared constant
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)


@admin.register(_get_model('Role'))
class RoleAdmin(admin.ModelAdmin):
    """Admin for Role model."""
    list_display = ('name', 'school', 'category', 'is_system_role', 'system_role_type')
    list_filter = ('category', 'is_system_role', 'school')
    search_fields = ('name', 'school__name', 'system_role_type')
    readonly_fields = ('is_system_role', 'system_role_type')
    
    def get_readonly_fields(self, request, obj=None):
        """Prevent editing system roles."""
        if obj and obj.is_system_role:
            return self.readonly_fields + ('name', 'category', 'permissions')
        return self.readonly_fields


@admin.register(_get_model('Profile'))
class ProfileAdmin(admin.ModelAdmin):
    """Admin for Profile model."""
    list_display = ('user', 'school', 'role', 'phone_number')
    list_filter = ('school', 'role__category')
    search_fields = ('user__email', 'school__name', 'role__name')
    raw_id_fields = ('user', 'school', 'role')


@admin.register(_get_model('Staff'))
class StaffAdmin(admin.ModelAdmin):
    """Admin for Staff model."""
    list_display = ('full_name', 'staff_id', 'school', 'position', 'is_active', 'is_teaching_staff')
    list_filter = ('is_active', 'is_teaching_staff', 'employment_type', 'school')
    search_fields = ('first_name', 'last_name', 'email', 'staff_id', 'position')
    readonly_fields = ('staff_id', 'user')
    fieldsets = (
        (None, {'fields': ('school', 'staff_id', 'user')}),
        ('Personal Information', {'fields': (
            'first_name', 'last_name', 'gender', 'date_of_birth',
            'marital_status', 'nationality', 'state_of_origin'
        )}),
        ('Contact Information', {'fields': (
            'email', PARENT_PHONE_FIELD, 'alternate_phone', 'address',  # ✅ Use shared constant
            'emergency_contact_name', 'emergency_contact_phone'
        )}),
        ('Employment Details', {'fields': (
            'position', 'department', 'employment_type', 'date_joined',
            'qualification', 'specialization', 'years_of_experience'
        )}),
        ('Bank & Official', {'fields': (
            'bank_name', 'account_number', 'account_name',
            'tax_identification_number', 'insurance_number'
        )}),
        ('Status', {'fields': ('is_active', 'is_teaching_staff', 'is_management')}),
        ('Metadata', {'fields': ('notes', 'medical_information', 'next_of_kin')}),
    )


@admin.register(_get_model('TeacherApplication'))
class TeacherApplicationAdmin(admin.ModelAdmin):
    """Admin for TeacherApplication model."""
    list_display = ('full_name', 'school', 'position_applied', 'status', 'created_at')
    list_filter = ('status', 'application_type', 'school')
    search_fields = ('first_name', 'last_name', 'email', 'position_applied', 'school__name')
    readonly_fields = ('created_at', 'updated_at', 'status_changed_at')
    fieldsets = (
        ('Application Details', {'fields': (
            'school', 'position', 'applicant', 'application_type'
        )}),
        ('Personal Information', {'fields': (
            'first_name', 'last_name', 'email', PARENT_PHONE_FIELD  # ✅ Use shared constant
        )}),
        ('Professional Information', {'fields': (
            'position_applied', 'years_of_experience',
            'qualification', 'specialization'
        )}),
        ('Application Content', {'fields': (
            'cover_letter', 'resume', 'certificates'
        )}),
        ('Status & Tracking', {'fields': (
            'status', 'status_changed_by', 'status_changed_at'
        )}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(_get_model('StaffInvitation'))
class StaffInvitationAdmin(admin.ModelAdmin):
    """Admin for StaffInvitation model."""
    list_display = ('email', 'school', 'role', 'status', 'created_at', 'expires_at')
    list_filter = ('status', 'school', 'role')
    search_fields = ('email', 'school__name', 'role__name')
    readonly_fields = ('token', 'created_at', 'expires_at')
    fieldsets = (
        (None, {'fields': ('school', 'email', 'role', 'status')}),
        ('Invitation Details', {'fields': ('token', 'invited_by', 'message')}),
        ('Timestamps', {'fields': ('created_at', 'expires_at')}),
    )


@admin.register(_get_model('OpenPosition'))
class OpenPositionAdmin(admin.ModelAdmin):
    """Admin for OpenPosition model."""
    list_display = ('title', 'school', 'department', 'is_active', 'created_at')
    list_filter = ('is_active', 'school')
    search_fields = ('title', 'school__name', 'department')
    fieldsets = (
        (None, {'fields': ('school', 'title', 'department', 'is_active')}),
        ('Details', {'fields': ('description', 'requirements')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    ) 