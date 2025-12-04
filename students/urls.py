# students/urls.py - COMPLETE VERSION
from django.urls import path
from . import views, views_parent

app_name = 'students'

urlpatterns = [
    # Student Management
    path('', views.student_list_view, name='student_list'),
    path('create/', views.student_create_view, name='student_create'),
    path('<int:student_id>/', views.student_detail_view, name='student_detail'),
    path('<int:student_id>/edit/', views.student_edit_view, name='student_edit'),
    path('<int:student_id>/delete/', views.student_delete_view, name='student_delete'),
    
    # Parent Management
    path('parents/', views.parent_list_view, name='parent_list'),
    path('parents/create/', views.parent_create_view, name='parent_create'),
    path('parents/<int:parent_id>/', views.parent_detail_view, name='parent_detail'),
    path('parents/<int:parent_id>/edit/', views.parent_edit_view, name='parent_edit'),
    path('parents/<int:parent_id>/delete/', views.parent_delete_view, name='parent_delete'),
    path('parents/<int:parent_id>/create-account/', views.parent_create_account_view, name='parent_create_account'),
    
    # Class Group Management
    path('classes/', views.class_group_list_view, name='class_group_list'),
    path('classes/create/', views.class_group_create_view, name='class_group_create'),
    path('classes/<int:class_group_id>/', views.class_group_detail_view, name='class_group_detail'),
    path('classes/<int:class_group_id>/edit/', views.class_group_edit_view, name='class_group_edit'),
    path('classes/<int:class_group_id>/delete/', views.class_group_delete_view, name='class_group_delete'),
    
    # Education Level Management
    path('levels/', views.education_level_list_view, name='education_level_list'),
    path('levels/create/', views.education_level_create_view, name='education_level_create'),
    path('levels/<int:level_id>/edit/', views.education_level_edit_view, name='education_level_edit'),
    path('levels/<int:level_id>/delete/', views.education_level_delete_view, name='education_level_delete'),
    
    # AJAX Endpoints
    path('ajax/class-groups/<int:level_id>/', views.get_class_groups_for_level, name='get_class_groups_for_level'),
    path('ajax/students/<int:class_group_id>/', views.get_students_for_class, name='get_students_for_class'),
    path('ajax/stats/', views.student_quick_stats, name='student_quick_stats'),
    
    # Parent Dashboard & Management
    path('parent/dashboard/', views_parent.parent_dashboard_view, name='parent_dashboard'),
    path('parent/children/', views_parent.parent_children_view, name='parent_children'),
    
  
    # Academic Term Management
    path('terms/', views.academic_term_list_view, name='academic_terms'),
    path('terms/create/', views.academic_term_create_view, name='academic_term_create'),
    path('terms/<int:term_id>/', views.academic_term_detail_view, name='academic_term_detail'),
    path('terms/<int:term_id>/edit/', views.academic_term_edit_view, name='academic_term_edit'),
    path('terms/<int:term_id>/suspend/', views.academic_term_suspend_view, name='academic_term_suspend'),
    path('terms/<int:term_id>/resume/', views.academic_term_resume_view, name='academic_term_resume'),
    path('terms/<int:term_id>/close/', views.academic_term_close_view, name='academic_term_close'),
]