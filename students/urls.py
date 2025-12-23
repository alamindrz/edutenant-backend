# students/urls.py
"""
CLEANED STUDENT URLS - Updated for new architecture
Consistent naming, removed ClassGroup references
"""
from django.urls import path
from . import views, views_parent

app_name = 'students'

urlpatterns = [
    # ============ STUDENT MANAGEMENT ============
    path('', views.student_list_view, name='student_list'),
    path('create/', views.student_create_view, name='student_create'),
    path('<int:student_id>/', views.student_detail_view, name='student_detail'),
    path('<int:student_id>/edit/', views.student_edit_view, name='student_edit'),
    path('<int:student_id>/delete/', views.student_delete_view, name='student_delete'),

    # ============ PARENT MANAGEMENT ============
    path('parents/', views.parent_list_view, name='parent_list'),
    path('parents/create/', views.parent_create_view, name='parent_create'),
    path('parents/<int:parent_id>/', views.parent_detail_view, name='parent_detail'),
    path('parents/<int:parent_id>/edit/', views.parent_edit_view, name='parent_edit'),
    path('parents/<int:parent_id>/delete/', views.parent_delete_view, name='parent_delete'),
    # Note: parent_create_account_view moved to parent detail page via POST

    # ============ EDUCATION LEVEL MANAGEMENT ============
    path('levels/', views.education_level_list_view, name='education_level_list'),
    path('levels/create/', views.education_level_create_view, name='education_level_create'),
    path('levels/<int:level_id>/edit/', views.education_level_edit_view, name='education_level_edit'),
    path('levels/<int:level_id>/delete/', views.education_level_delete_view, name='education_level_delete'),

    # ============ ACADEMIC TERM MANAGEMENT ============
    path('terms/', views.academic_term_list_view, name='academic_terms'),
    path('terms/create/', views.academic_term_create_view, name='academic_term_create'),
    path('terms/<int:term_id>/', views.academic_term_detail_view, name='academic_term_detail'),
    path('terms/<int:term_id>/edit/', views.academic_term_edit_view, name='academic_term_edit'),
    path('terms/<int:term_id>/delete/', views.academic_term_delete_view, name='academic_term_delete'),
    # path('terms/<int:term_id>/suspend/', views.academic_term_suspend_view, name='academic_term_suspend'),
    #path('terms/<int:term_id>/resume/', views.academic_term_resume_view, name='academic_term_resume'),
   # path('terms/<int:term_id>/close/', views.academic_term_close_view, name='academic_term_close'),

    # ============ PARENT-SPECIFIC VIEWS ============
    path('parent/dashboard/', views_parent.parent_dashboard_view, name='parent_dashboard'),
    path('parent/children/', views_parent.parent_children_view, name='parent_children'),
    path('parent/applications/', views_parent.parent_applications_view, name='parent_applications'),
    path('parent/applications/<int:application_id>/', views_parent.parent_application_detail_view, name='parent_application_detail'),
    path('parent/payments/', views_parent.parent_payment_view, name='parent_payment'),
    path('parent/school-dashboard/', views_parent.parent_school_dashboard_view, name='parent_school_dashboard'),

    # ============ AJAX ENDPOINTS ============
    path('ajax/classes-for-level/<int:level_id>/', views.get_classes_for_level, name='get_classes_for_level'),
    path('ajax/students-for-class/<int:class_id>/', views.get_students_for_class, name='get_students_for_class'),
    path('ajax/stats/', views.student_quick_stats, name='student_quick_stats'),

    # Parent AJAX endpoints
    path('ajax/parent/invoices/', views_parent.parent_invoices_partial, name='parent_invoices_partial'),
    path('ajax/parent/children/', views_parent.parent_children_partial, name='parent_children_partial'),
    path('ajax/parent/stats/', views_parent.parent_stats_ajax, name='parent_stats_ajax'),
    path('ajax/parent/notifications/', views_parent.parent_notifications_ajax, name='parent_notifications_ajax'),
]

# ============ HTMX PATTERNS (for reference) ============
"""
HTMX patterns that should be included in templates:

1. Dynamic class loading:
   - Add to education_level field: hx-get="/students/ajax/classes-for-level/"

2. Parent dashboard updates:
   - Use: hx-get="/students/ajax/parent/stats/"
   - Use: hx-get="/students/ajax/parent/invoices/"

3. Real-time statistics:
   - Use: hx-get="/students/ajax/stats/"

Note: All HTMX endpoints should be documented in template comments
"""
