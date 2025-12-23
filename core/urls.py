# core/urls.py
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Theme toggle
    path('theme/toggle/', views.toggle_theme_view, name='toggle_theme'),
    
    # Class Categories
    path('class-categories/', views.class_category_list_view, name='class_category_list'),
    path('class-categories/create/', views.class_category_create_view, name='class_category_create'),
    path('class-categories/<int:category_id>/edit/', views.class_category_edit_view, name='class_category_edit'),
    path('class-categories/<int:category_id>/delete/', views.class_category_delete_view, name='class_category_delete'),
    
    # Classes
    path('classes/', views.class_list_view, name='class_list'),
    path('classes/create/', views.class_create_view, name='class_create'),
    path('classes/<int:pk>/update/', views.class_update_view, name='class_update'),
    path('classes/<int:class_id>/', views.class_detail_view, name='class_detail'),
    path('classes/<int:class_id>/delete/', views.class_delete_view, name='class_delete'),
    
    # Class Subjects
    path('classes/<int:class_id>/subjects/add/', views.class_subject_add_view, name='class_subject_add'),
    path('classes/<int:class_id>/subjects/<int:subject_id>/edit/', views.class_subject_edit_view, name='class_subject_edit'),
    path('classes/<int:class_id>/subjects/<int:subject_id>/remove/', views.class_subject_remove_view, name='class_subject_remove'),
    
    # Class Monitors
    path('classes/<int:class_id>/monitors/assign/', views.class_monitor_assign_view, name='class_monitor_assign'),
    path('classes/<int:class_id>/monitors/<int:monitor_id>/remove/', views.class_monitor_remove_view, name='class_monitor_remove'),
    
    # Subjects
    path('subjects/', views.subject_list_view, name='subject_list'),
    path('subjects/create/', views.subject_create_view, name='subject_create'),
    path('subjects/<int:subject_id>/', views.subject_detail_view, name='subject_detail'),
    path('subjects/<int:subject_id>/edit/', views.subject_edit_view, name='subject_edit'),
    path('subjects/<int:subject_id>/delete/', views.subject_delete_view, name='subject_delete'),
    
    # HTMX/AJAX Endpoints
    path('ajax/classes-for-category/<int:category_id>/', views.get_classes_for_category, name='get_classes_for_category'),
    path('ajax/class-stats/', views.get_class_stats, name='get_class_stats'),
    path('ajax/class-bulk-actions/', views.class_bulk_actions_view, name='class_bulk_actions'),
    path('ajax/school-overview-stats/', views.school_overview_stats, name='school_overview_stats'),
] 