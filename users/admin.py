# users/admin.py - UPDATED
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, School, Role, Profile

@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active')
    list_filter = ('is_staff', 'is_active', 'is_superuser')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal info'), {'fields': ('first_name', 'last_name', 'phone_number')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
        (_('Multi-tenant'), {'fields': ('current_school',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)

# Keep the other admin classes the same...
@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'subdomain', 'subdomain_status', 'is_active')
    list_filter = ('subdomain_status', 'is_active')
    search_fields = ('name', 'subdomain')

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'school', 'category', 'is_system_role')
    list_filter = ('category', 'is_system_role')
    search_fields = ('name', 'school__name')

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'school', 'role')
    list_filter = ('school', 'role')
    search_fields = ('user__email', 'school__name')