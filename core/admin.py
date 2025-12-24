# core/admin.py - CREATE OR UPDATE THIS FILE
from django.contrib import admin
from .models import Subject, Class, ClassCategory, ClassSubject, ClassCreationTemplate

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'category', 'school', 'is_active']
    list_filter = ['category', 'difficulty_level', 'is_active', 'school']
    search_fields = ['name', 'code', 'description']
    list_editable = ['is_active']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(school=request.school)

# Register other core models
admin.site.register(ClassCategory)
admin.site.register(Class)
admin.site.register(ClassSubject)
admin.site.register(ClassCreationTemplate)
