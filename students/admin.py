# students/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from .models import Student, Parent, Attendance, Score, Enrollment, EducationLevel, AcademicTerm

# ===== STUDENT ADMIN =====
@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = [
        'admission_number', 
        'full_name_display', 
        'current_class', 
        'parent_link',
        'admission_status',
        'is_staff_child_display'
    ]
    
    list_filter = [
        'admission_status',
        'gender',
        'is_staff_child',
        'current_class__school'
    ]
    
    search_fields = [
        'first_name',
        'last_name', 
        'admission_number',
        'parent__first_name',
        'parent__last_name',
        'parent__email'
    ]
    
    raw_id_fields = ['parent', 'current_class', 'education_level']
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'admission_number',
        'full_name_display',
        'age_display'
    ]
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                'first_name',
                'last_name',
                'gender',
                'date_of_birth',
                'age_display'
            )
        }),
        ('School Information', {
            'fields': (
                'admission_number',
                'admission_status',
                'current_class',
                'education_level',
                'application_date',
                'admission_date'
            )
        }),
        ('Parent/Guardian', {
            'fields': (
                'parent',
                'is_staff_child',
            )
        }),
        ('Previous Education', {
            'fields': (
                'previous_school',
                'previous_class',
                'application_notes'
            )
        }),
        ('Additional Information', {
            'fields': (
                'medical_conditions',
                'allergies',
                'emergency_contact',
                'emergency_contact_relationship',
                'nationality',
                'state_of_origin',
                'religion'
            ),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def full_name_display(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name_display.short_description = 'Name'
    
    def parent_link(self, obj):
        if obj.parent:
            url = reverse('admin:students_parent_change', args=[obj.parent.id])
            return format_html('<a href="{}">{}</a>', url, obj.parent.full_name)
        return "No Parent"
    parent_link.short_description = 'Parent'
    
    def is_staff_child_display(self, obj):
        return "Yes" if obj.is_staff_child else "No"
    is_staff_child_display.short_description = 'Staff Child'
    is_staff_child_display.boolean = True
    
    def age_display(self, obj):
        return obj.age if hasattr(obj, 'age') else "N/A"
    age_display.short_description = 'Age'

# ===== PARENT ADMIN =====
@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
    list_display = [
        'full_name_display',
        'email',
        'phone_number',
        'school',
        'is_staff_child_display',
        'student_count'
    ]
    
    list_filter = [
        'school',
        'is_staff_child',
        'relationship'
    ]
    
    search_fields = [
        'first_name',
        'last_name',
        'email',
        'phone_number'
    ]
    
    raw_id_fields = ['user', 'staff_member']
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'full_name_display',
        'student_count'
    ]
    
    fieldsets = (
        ('Personal Information', {
            'fields': (
                'first_name',
                'last_name',
                'email',
                'phone_number',
                'address',
                'relationship'
            )
        }),
        ('School Information', {
            'fields': (
                'school',
                'is_staff_child',
                'staff_member'
            )
        }),
        ('Account', {
            'fields': (
                'user',
            )
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
                'student_count'
            ),
            'classes': ('collapse',)
        }),
    )
    
    def full_name_display(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name_display.short_description = 'Name'
    
    def is_staff_child_display(self, obj):
        return "Yes" if obj.is_staff_child else "No"
    is_staff_child_display.short_description = 'Staff Child'
    is_staff_child_display.boolean = True
    
    def student_count(self, obj):
        return obj.students.count()
    student_count.short_description = 'Children'

# ===== ATTENDANCE ADMIN =====
@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = [
        'student_display',
        'date',
        'status_display',
        'academic_term_display',
        'recorded_by_display'
    ]
    
    list_filter = [
        'status',
        'date',
        'academic_term'
    ]
    
    search_fields = [
        'student__first_name',
        'student__last_name',
        'student__admission_number'
    ]
    
    raw_id_fields = ['student', 'academic_term', 'recorded_by']
    
    readonly_fields = [
        'recorded_at',
        'student_display',
        'academic_term_display',
        'recorded_by_display'
    ]
    
    fieldsets = (
        ('Attendance Details', {
            'fields': (
                'student',
                'academic_term',
                'date',
                'status',
                'time_in',
                'time_out',
                'remarks'
            )
        }),
        ('Recorded By', {
            'fields': (
                'recorded_by',
                'recorded_by_display',
                'recorded_at'
            )
        }),
    )
    
    def student_display(self, obj):
        return obj.student.full_name if obj.student else "N/A"
    student_display.short_description = 'Student'
    
    def academic_term_display(self, obj):
        return str(obj.academic_term) if obj.academic_term else "N/A"
    academic_term_display.short_description = 'Academic Term'
    
    def recorded_by_display(self, obj):
        if obj.recorded_by:
            return obj.recorded_by.user.get_full_name() if hasattr(obj.recorded_by, 'user') else str(obj.recorded_by)
        return "N/A"
    recorded_by_display.short_description = 'Recorded By'
    
    def status_display(self, obj):
        status_colors = {
            'present': 'green',
            'absent': 'red',
            'late': 'orange',
            'excused': 'blue',
            'sick': 'purple',
            'other': 'gray'
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'

# ===== SCORE ADMIN =====
@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = [
        'student_display',
        'subject',
        'score_display',
        'grade_display',
        'assessment_type',
        'assessment_date'
    ]
    
    list_filter = [
        'subject',
        'assessment_type',
        'assessment_date'
    ]
    
    search_fields = [
        'enrollment__student__first_name',
        'enrollment__student__last_name',
        'subject__name'
    ]
    
    raw_id_fields = ['enrollment', 'subject', 'recorded_by']
    
    readonly_fields = [
        'recorded_at',
        'student_display',
        'grade_display',
        'percentage_display',
        'recorded_by_display'
    ]
    
    fieldsets = (
        ('Score Details', {
            'fields': (
                'enrollment',
                'subject',
                'score',
                'maximum_score',
                'score_display',
                'percentage_display',
                'grade_display'
            )
        }),
        ('Assessment Information', {
            'fields': (
                'assessment_type',
                'assessment_name',
                'assessment_date',
                'remarks'
            )
        }),
        ('Recorded By', {
            'fields': (
                'recorded_by',
                'recorded_by_display',
                'recorded_at'
            )
        }),
    )
    
    def student_display(self, obj):
        if obj.enrollment and obj.enrollment.student:
            return obj.enrollment.student.full_name
        return "N/A"
    student_display.short_description = 'Student'
    
    def score_display(self, obj):
        return f"{obj.score}/{obj.maximum_score}"
    score_display.short_description = 'Score'
    
    def percentage_display(self, obj):
        return f"{obj.percentage:.1f}%"
    percentage_display.short_description = 'Percentage'
    
    def grade_display(self, obj):
        grade_colors = {
            'A': 'green',
            'AB': 'lightgreen',
            'B': 'blue',
            'BC': 'lightblue',
            'C': 'orange',
            'CD': 'gold',
            'D': 'red',
            'E': 'darkred',
            'F': 'darkred'
        }
        color = grade_colors.get(obj.grade, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.grade
        )
    grade_display.short_description = 'Grade'
    
    def recorded_by_display(self, obj):
        if obj.recorded_by:
            return obj.recorded_by.user.get_full_name() if hasattr(obj.recorded_by, 'user') else str(obj.recorded_by)
        return "N/A"
    recorded_by_display.short_description = 'Recorded By'

# ===== ENROLLMENT ADMIN =====
@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = [
        'student_display',
        'academic_term_display',
        'enrollment_type_display',
        'is_active_display',
        'enrollment_date'
    ]
    
    list_filter = [
        'is_active',
        'enrollment_type',
        'academic_term'
    ]
    
    search_fields = [
        'student__first_name',
        'student__last_name'
    ]
    
    raw_id_fields = ['student', 'academic_term']
    
    readonly_fields = [
        'enrollment_date',
        'student_display',
        'academic_term_display',
        'enrollment_type_display',
        'is_active_display'
    ]
    
    fieldsets = (
        ('Enrollment Details', {
            'fields': (
                'student',
                'academic_term',
                'enrollment_type',
                'is_active',
                'enrollment_date',
                'notes'
            )
        }),
    )
    
    def student_display(self, obj):
        return obj.student.full_name if obj.student else "N/A"
    student_display.short_description = 'Student'
    
    def academic_term_display(self, obj):
        return str(obj.academic_term) if obj.academic_term else "N/A"
    academic_term_display.short_description = 'Academic Term'
    
    def enrollment_type_display(self, obj):
        type_colors = {
            'new': 'green',
            'continuing': 'blue',
            'transfer': 'orange'
        }
        color = type_colors.get(obj.enrollment_type, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_enrollment_type_display()
        )
    enrollment_type_display.short_description = 'Type'
    
    def is_active_display(self, obj):
        return "Yes" if obj.is_active else "No"
    is_active_display.short_description = 'Active'
    is_active_display.boolean = True

# ===== EDUCATION LEVEL ADMIN =====
@admin.register(EducationLevel)
class EducationLevelAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'level_display',
        'order',
        'school'
    ]
    
    list_filter = [
        'school',
        'level'
    ]
    
    search_fields = [
        'name',
        'description'
    ]
    
    readonly_fields = []
    
    fieldsets = (
        ('Level Information', {
            'fields': (
                'name',
                'level',
                'description',
                'order'
            )
        }),
        ('School Information', {
            'fields': (
                'school',
            )
        }),
    )
    
    def level_display(self, obj):
        level_colors = {
            'nursery': 'pink',
            'primary': 'green',
            'jss': 'blue',
            'sss': 'purple'
        }
        color = level_colors.get(obj.level, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_level_display()
        )
    level_display.short_description = 'Level'

# ===== ACADEMIC TERM ADMIN =====
@admin.register(AcademicTerm)
class AcademicTermAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'academic_year',
        'term_display',
        'start_date',
        'end_date',
        'status_display',
        'is_active_display'
    ]
    
    list_filter = [
        'school',
        'academic_year',
        'term',
        'status',
        'is_active'
    ]
    
    search_fields = [
        'name',
        'academic_year'
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'progress_percentage_display',
        'is_current_display'
    ]
    
    fieldsets = (
        ('Term Information', {
            'fields': (
                'school',
                'name',
                'term',
                'academic_year',
                'status',
                'is_active'
            )
        }),
        ('Dates', {
            'fields': (
                'start_date',
                'end_date',
                'actual_end_date',
                'mid_term_break_start',
                'mid_term_break_end',
                'closure_start',
                'closure_end',
                'closure_reason'
            )
        }),
        ('Duration', {
            'fields': (
                'planned_weeks',
                'actual_weeks',
            )
        }),
        ('Status', {
            'fields': (
                'progress_percentage_display',
                'is_current_display',
            )
        }),
        ('Metadata', {
            'fields': (
                'created_at',
                'updated_at',
            ),
            'classes': ('collapse',)
        }),
    )
    
    def term_display(self, obj):
        term_colors = {
            'first': 'green',
            'second': 'blue',
            'third': 'orange'
        }
        color = term_colors.get(obj.term, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_term_display()
        )
    term_display.short_description = 'Term'
    
    def status_display(self, obj):
        status_colors = {
            'upcoming': 'gray',
            'active': 'green',
            'completed': 'blue',
            'suspended': 'red',
            'extended': 'orange'
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def is_active_display(self, obj):
        return "Yes" if obj.is_active else "No"
    is_active_display.short_description = 'Active'
    is_active_display.boolean = True
    
    def progress_percentage_display(self, obj):
        return f"{obj.progress_percentage}%"
    progress_percentage_display.short_description = 'Progress'
    
    def is_current_display(self, obj):
        return "Yes" if obj.is_current else "No"
    is_current_display.short_description = 'Current Term'
    is_current_display.boolean = True