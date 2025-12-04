# attendance/urls.py - ADD MISSING URL
from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # Dashboard
    path('', views.attendance_dashboard_view, name='dashboard'),
    
    # Student Attendance
    path('students/', views.student_attendance_list_view, name='student_attendance_list'),
    
    # Class Group Attendance
    path('class-groups/', views.class_group_attendance_view, name='class_group_attendance'),
    path('classes/', views.class_attendance_view, name='class_attendance'),  # ADD THIS LINE
    
    # Teacher Attendance
    path('teachers/', views.teacher_attendance_list_view, name='teacher_attendance_list'),
    path('teachers/<int:staff_id>/signin/', views.teacher_signin_view, name='teacher_signin'),
    path('teachers/<int:staff_id>/signout/', views.teacher_signout_view, name='teacher_signout'),
    
    # Reports
    path('reports/', views.attendance_reports_view, name='reports'),
    
    # HTMX Endpoints
    path('partial/student-table/', views.student_attendance_table_partial, name='student_attendance_table_partial'),
]