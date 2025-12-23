# attendance/urls.py 
from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # Dashboard
    path('', views.attendance_dashboard_view, name='dashboard'),
    
    # Student Attendance
    path('students/', views.student_attendance_list_view, name='student_attendance_list'),
    
    # Class Attendance (using core.Class, NOT ClassGroup)
    path('classes/', views.class_attendance_view, name='class_attendance'),
    
    # Teacher Attendance
    path('teachers/', views.teacher_attendance_list_view, name='teacher_attendance_list'),
    path('teachers/<int:staff_id>/signin/', views.teacher_signin_view, name='teacher_signin'),
    path('teachers/<int:staff_id>/signout/', views.teacher_signout_view, name='teacher_signout'),
    
    # Reports
    path('reports/', views.attendance_reports_view, name='reports'),
    
    # HTMX Endpoints
    path('partial/student-table/', views.student_attendance_table_partial, name='student_attendance_table_partial'),
    
    # ✅ Added new HTMX endpoints for better UX
    path('api/stats/', views.get_attendance_stats_api, name='attendance_stats_api'),
]

# ============ URL PATTERN EXPLANATIONS ============

"""
URL Structure:
/attendance/                           - Dashboard overview
/attendance/students/                  - List student attendance
/attendance/classes/                   - List class attendance (core.Class based)
/attendance/teachers/                  - List teacher attendance
/attendance/teachers/<id>/signin/      - Teacher sign-in
/attendance/teachers/<id>/signout/     - Teacher sign-out
/attendance/reports/                   - Attendance reports
/attendance/partial/student-table/     - HTMX table partial
/attendance/api/stats/                 - JSON API for stats
"""

# ============ SUGGESTED ADDITIONAL URLS ============

"""
Consider adding these URLs for a complete attendance system:

# Individual student attendance
path('students/<int:student_id>/', views.student_attendance_detail, name='student_attendance_detail'),

# Individual teacher attendance
path('teachers/<int:staff_id>/', views.teacher_attendance_detail, name='teacher_attendance_detail'),

# Attendance configuration
path('config/', views.attendance_config_view, name='attendance_config'),

# Bulk attendance actions
path('bulk/update/', views.bulk_attendance_update, name='bulk_attendance_update'),

# Import/Export
path('import/', views.attendance_import_view, name='attendance_import'),
path('export/', views.attendance_export_view, name='attendance_export'),

# Mobile/API endpoints
path('api/checkin/', views.api_student_checkin, name='api_student_checkin'),
path('api/checkout/', views.api_student_checkout, name='api_student_checkout'),

# Notifications
path('notifications/', views.attendance_notifications_view, name='attendance_notifications'),
""" 