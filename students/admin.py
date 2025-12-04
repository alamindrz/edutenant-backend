# students/admin.py
from django.contrib import admin
from .models import (
    EducationLevel, ClassGroup, Parent, Student, AcademicTerm, Enrollment, Attendance, Score
)


@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = ['name', 'academic_year', 'term', 'school', 'start_date', 'end_date', 'status', 'is_active']
    list_filter = ['school', 'academic_year', 'term', 'status', 'is_active']
    search_fields = ['name', 'academic_year']
    date_hierarchy = 'start_date'
    actions = ['activate_terms', 'suspend_terms', 'close_terms']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('school', 'name', 'term', 'academic_year')
        }),
        ('Dates', {
            'fields': ('start_date', 'end_date', 'planned_weeks', 'actual_end_date', 'actual_weeks')
        }),
        ('Status', {
            'fields': ('status', 'is_active')
        }),
        ('Breaks & Closures', {
            'fields': ('mid_term_break_start', 'mid_term_break_end', 'closure_start', 'closure_end', 'closure_reason'),
            'classes': ('collapse',)
        }),
    )
    
    def activate_terms(self, request, queryset):
        updated = queryset.update(status='active', is_active=True)
        self.message_user(request, f'{updated} terms activated.')
    activate_terms.short_description = "Activate selected terms"
    
    def suspend_terms(self, request, queryset):
        updated = queryset.update(status='suspended', is_active=False)
        self.message_user(request, f'{updated} terms suspended.')
    suspend_terms.short_description = "Suspend selected terms"
    
    def close_terms(self, request, queryset):
        updated = queryset.update(status='closed', is_active=False)
        self.message_user(request, f'{updated} terms closed.')
    close_terms.short_description = "Close selected terms"


@admin.register(EducationLevel)
class EducationLevelAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'school', 'order')
    list_filter = ('level', 'school')
    search_fields = ('name', 'school__name')

@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'education_level', 'school', 'class_teacher', 'student_count')
    list_filter = ('education_level', 'school')
    search_fields = ('name', 'school__name')
    
    def student_count(self, obj):
        return obj.student_set.count()

@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone_number', 'school', 'children_count')
    list_filter = ('school',)
    search_fields = ('first_name', 'last_name', 'email')
    
    def children_count(self, obj):
        return obj.student_set.count()

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'admission_number', 'parent', 'education_level', 'class_group', 'is_active')
    list_filter = ('education_level', 'class_group', 'is_active', 'school')
    search_fields = ('first_name', 'last_name', 'admission_number', 'parent__first_name')
    raw_id_fields = ('parent',)



admin.site.register(Enrollment)
admin.site.register(Attendance)
admin.site.register(Score)