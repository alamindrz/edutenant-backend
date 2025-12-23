# core/views.py
"""
CLEANED CORE VIEWS - Using shared architecture
NO circular imports, PROPER service usage, WELL LOGGED
"""
import logging
import csv
from decimal import Decimal
from typing import Optional, List, Dict, Any

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.db.models import Q, Count, Sum, F, Avg  # Added Avg
from django.core.paginator import Paginator
from django.apps import apps
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from datetime import timedelta

# SHARED IMPORTS
from shared.decorators.permissions import require_role, require_school_context
from shared.constants.model_fields import StatusChoices, CLASS_MODEL_PATH
from shared.utils.field_mapping import FieldMapper
from shared.models.class_manager import ClassManager

# LOCAL IMPORTS
from .forms import SubjectForm, ClassForm, ClassCategoryForm, ClassSubjectForm

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'core'):
    """Get model lazily to avoid circular imports."""
    try:
        return apps.get_model(app_label, model_name)
    except LookupError as e:
        logger.error(f"Model not found: {app_label}.{model_name} - {e}")
        raise


def recover_school_context(request) -> Optional[Any]:
    """Recover school context when middleware fails."""
    if hasattr(request, 'user') and request.user.is_authenticated:
        # Method 1: User's current_school
        if hasattr(request.user, 'current_school') and request.user.current_school:
            return request.user.current_school

        # Method 2: First profile school
        try:
            Profile = _get_model('Profile', 'users')
            profile = Profile.objects.filter(user=request.user).first()
            if profile:
                # Update user's current_school for consistency
                request.user.current_school = profile.school
                request.user.save()
                return profile.school
        except Exception as e:
            logger.error(f"School recovery failed: {e}", exc_info=True)

    return None


# ============ THEME VIEW ============

@login_required
def toggle_theme_view(request):
    """Toggle between light and dark theme with HTMX support."""
    current_theme = request.session.get('theme', 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    request.session['theme'] = new_theme
    request.session.modified = True

    return JsonResponse({
        'theme': new_theme,
        'message': f'Switched to {new_theme} mode'
    })


# ============ CLASS CATEGORY VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def class_category_list_view(request):
    """List all class categories for the current school."""
    school = request.school

    ClassCategory = _get_model('ClassCategory')

    categories = ClassCategory.objects.filter(school=school).annotate(
        class_count=Count('classes', filter=Q(classes__is_active=True))
    ).order_by('display_order', 'name')

    context = {'categories': categories}
    return render(request, 'core/class_category_list.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_category_create_view(request):
    """Create new class category."""
    school = request.school

    if request.method == 'POST':
        form = ClassCategoryForm(request.POST)
        if form.is_valid():
            try:
                category = form.save(commit=False)
                category.school = school
                category.save()

                messages.success(request, f"Class category '{category.name}' created successfully!")
                return redirect('core:class_category_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error creating class category: {e}", exc_info=True)
                messages.error(request, f"Error creating class category: {str(e)}")
    else:
        form = ClassCategoryForm()

    context = {'form': form, 'page_title': 'Create Class Category'}
    return render(request, 'core/class_category_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_category_edit_view(request, category_id):
    """Edit existing class category."""
    school = request.school
    ClassCategory = _get_model('ClassCategory')

    category = get_object_or_404(ClassCategory, id=category_id, school=school)

    if request.method == 'POST':
        form = ClassCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Class category '{category.name}' updated successfully!")
                return redirect('core:class_category_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating class category: {e}", exc_info=True)
                messages.error(request, f"Error updating class category: {str(e)}")
    else:
        form = ClassCategoryForm(instance=category)

    context = {
        'form': form,
        'category': category,
        'page_title': f'Edit Class Category: {category.name}'
    }
    return render(request, 'core/class_category_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_category_delete_view(request, category_id):
    """Delete class category (only if empty)."""
    school = request.school
    ClassCategory = _get_model('ClassCategory')
    Class = _get_model('Class')

    category = get_object_or_404(ClassCategory, id=category_id, school=school)

    # Check if category has classes
    if Class.objects.filter(category=category, is_active=True).exists():
        messages.error(request, f"Cannot delete category '{category.name}'. It contains active classes.")
        return redirect('core:class_category_list')

    if request.method == 'POST':
        try:
            category_name = category.name
            category.delete()
            messages.success(request, f"Class category '{category_name}' deleted successfully!")
            return redirect('core:class_category_list')

        except Exception as e:
            logger.error(f"Error deleting class category: {e}", exc_info=True)
            messages.error(request, f"Error deleting class category: {str(e)}")

    context = {
        'category': category,
        'page_title': f'Delete Class Category: {category.name}'
    }
    return render(request, 'core/class_category_confirm_delete.html', context)


# ============ CLASS VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def class_list_view(request):
    """List all classes for the current school."""
    school = request.school

    Class = _get_model('Class')
    ClassCategory = _get_model('ClassCategory')

    # Get all classes with annotations
    classes = Class.objects.filter(school=school).select_related(
        'category', 'form_master', 'assistant_form_master', 'education_level'
    ).annotate(
        student_count=Count('students', filter=Q(students__is_active=True, students__admission_status='enrolled'))
    ).order_by('category__display_order', 'name')

    # Filters
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', 'active')
    class_type_filter = request.GET.get('type', '')

    if category_filter:
        classes = classes.filter(category_id=category_filter)

    if status_filter == 'inactive':
        classes = classes.filter(is_active=False)
    elif status_filter == 'all':
        # Already have all classes
        pass
    else:
        classes = classes.filter(is_active=True)

    if class_type_filter:
        classes = classes.filter(class_type=class_type_filter)

    if search_query:
        classes = classes.filter(
            Q(name__icontains=search_query) |
            Q(room_number__icontains=search_query) |
            Q(form_master__first_name__icontains=search_query) |
            Q(form_master__last_name__icontains=search_query) |
            Q(category__name__icontains=search_query) |
            Q(education_level__name__icontains=search_query)
        )

    categories = ClassCategory.objects.filter(school=school, is_active=True)

    # Class type choices
    class_types = [choice[0] for choice in Class.CLASS_TYPES]

    # Return partial for HTMX requests
    template = 'core/partials/class_table.html' if request.headers.get('HX-Request') else 'core/class_list.html'

    context = {
        'classes': classes,
        'categories': categories,
        'search_query': search_query,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'class_type_filter': class_type_filter,
        'class_types': class_types,
        'total_count': classes.count(),
        'active_count': classes.filter(is_active=True).count(),
    }
    return render(request, template, context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_create_view(request):
    """Create new class."""
    school = request.school

    if request.method == 'POST':
        form = ClassForm(request.POST, school=school)
        if form.is_valid():
            try:
                class_instance = form.save(commit=False)
                class_instance.school = school
                class_instance.save()

                # Update class strength
                class_instance.update_strength()

                messages.success(request, f"Class '{class_instance.name}' created successfully!")
                return redirect('core:class_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error creating class: {e}", exc_info=True)
                messages.error(request, f"Error creating class: {str(e)}")
    else:
        form = ClassForm(school=school)

    context = {
        'form': form,
        'page_title': 'Create New Class',
        'action': 'create'
    }
    return render(request, 'core/class_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_update_view(request, class_id):  # Changed parameter name from pk to class_id
    """Update existing class."""
    school = request.school
    Class = _get_model('Class')

    class_instance = get_object_or_404(Class, id=class_id, school=school)  # Changed pk to id

    if request.method == 'POST':
        form = ClassForm(request.POST, instance=class_instance, school=school)
        if form.is_valid():
            try:
                class_instance = form.save()

                # Update class strength
                class_instance.update_strength()

                messages.success(request, f"Class '{class_instance.name}' updated successfully!")

                if request.headers.get('HX-Request'):
                    # Return class row for HTMX update
                    return render(request, 'core/partials/class_row.html', {
                        'class_instance': class_instance
                    })
                return redirect('core:class_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating class: {e}", exc_info=True)
                messages.error(request, f"Error updating class: {str(e)}")
    else:
        form = ClassForm(instance=class_instance, school=school)

    context = {
        'form': form,
        'class_instance': class_instance,
        'page_title': f'Update {class_instance.name}',
        'action': 'update'
    }
    return render(request, 'core/class_form.html', context)


@login_required
@require_school_context
def class_detail_view(request, class_id):
    """View class details."""
    school = request.school
    Class = _get_model('Class')
    ClassSubject = _get_model('ClassSubject')
    ClassMonitor = _get_model('ClassMonitor')

    class_instance = get_object_or_404(Class, id=class_id, school=school)

    # Get class subjects
    class_subjects = ClassSubject.objects.filter(
        class_instance=class_instance
    ).select_related('subject', 'teacher').order_by('display_order')

    # Get class monitors
    class_monitors = ClassMonitor.objects.filter(
        class_instance=class_instance,
        is_active=True
    ).select_related('student').order_by('role')

    # Get students in this class
    Student = _get_model('Student', 'students')
    students = Student.objects.filter(
        current_class=class_instance,
        is_active=True,
        admission_status__in=['enrolled', 'accepted']
    ).select_related('parent', 'education_level')

    # Check user permissions
    try:
        Profile = _get_model('Profile', 'users')
        profile = Profile.objects.get(user=request.user, school=school)

        # Teachers can only view their own classes
        if profile.role.system_role_type == 'teacher':
            if class_instance.form_master != profile.staff_profile and \
               class_instance.assistant_form_master != profile.staff_profile:
                # Check if teacher teaches any subject in this class
                if not class_subjects.filter(teacher=profile.staff_profile).exists():
                    raise PermissionDenied("You don't have permission to view this class.")

    except Profile.DoesNotExist:
        raise PermissionDenied("No profile found for this school.")

    context = {
        'class_instance': class_instance,
        'class_subjects': class_subjects,
        'class_monitors': class_monitors,
        'students': students,
        'capacity_percentage': class_instance.capacity_percentage,
        'available_seats': class_instance.available_seats,
    }
    return render(request, 'core/class_detail.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_delete_view(request, class_id):
    """Delete class (soft delete)."""
    school = request.school
    Class = _get_model('Class')
    Student = _get_model('Student', 'students')

    class_instance = get_object_or_404(Class, id=class_id, school=school)

    # Check if class has students
    if Student.objects.filter(current_class=class_instance, is_active=True).exists():
        messages.error(request, f"Cannot delete class '{class_instance.name}'. It has students assigned.")
        return redirect('core:class_detail', class_id=class_instance.id)

    if request.method == 'POST':
        try:
            class_instance.is_active = False
            class_instance.save()
            messages.success(request, f"Class '{class_instance.name}' deactivated successfully!")
            return redirect('core:class_list')

        except Exception as e:
            logger.error(f"Error deleting class: {e}", exc_info=True)
            messages.error(request, f"Error deleting class: {str(e)}")

    context = {
        'class_instance': class_instance,
        'page_title': f'Deactivate Class: {class_instance.name}'
    }
    return render(request, 'core/class_confirm_delete.html', context)


# ============ CLASS SUBJECT VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def class_subject_add_view(request, class_id):
    """Add subject to class."""
    school = request.school
    Class = _get_model('Class')

    class_instance = get_object_or_404(Class, id=class_id, school=school)

    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, school=school)
        if form.is_valid():
            try:
                class_subject = form.save(commit=False)
                class_subject.class_instance = class_instance
                class_subject.save()

                messages.success(request, f"Subject '{class_subject.subject.name}' added to class!")
                return redirect('core:class_detail', class_id=class_instance.id)

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error adding subject to class: {e}", exc_info=True)
                messages.error(request, f"Error adding subject to class: {str(e)}")
    else:
        form = ClassSubjectForm(school=school)

    context = {
        'form': form,
        'class_instance': class_instance,
        'page_title': f'Add Subject to {class_instance.name}'
    }
    return render(request, 'core/class_subject_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_subject_edit_view(request, class_id, subject_id):
    """Edit class subject assignment."""
    school = request.school
    Class = _get_model('Class')
    ClassSubject = _get_model('ClassSubject')

    class_instance = get_object_or_404(Class, id=class_id, school=school)
    class_subject = get_object_or_404(ClassSubject, class_instance=class_instance, id=subject_id)

    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, instance=class_subject, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, "Subject assignment updated successfully!")
                return redirect('core:class_detail', class_id=class_instance.id)

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating subject assignment: {e}", exc_info=True)
                messages.error(request, f"Error updating subject assignment: {str(e)}")
    else:
        form = ClassSubjectForm(instance=class_subject, school=school)

    context = {
        'form': form,
        'class_instance': class_instance,
        'class_subject': class_subject,
        'page_title': 'Edit Subject Assignment'
    }
    return render(request, 'core/class_subject_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_subject_remove_view(request, class_id, subject_id):
    """Remove subject from class."""
    school = request.school
    Class = _get_model('Class')
    ClassSubject = _get_model('ClassSubject')

    class_instance = get_object_or_404(Class, id=class_id, school=school)
    class_subject = get_object_or_404(ClassSubject, class_instance=class_instance, id=subject_id)

    if request.method == 'POST':
        try:
            subject_name = class_subject.subject.name
            class_subject.delete()
            messages.success(request, f"Subject '{subject_name}' removed from class!")
            return redirect('core:class_detail', class_id=class_instance.id)

        except Exception as e:
            logger.error(f"Error removing subject: {e}", exc_info=True)
            messages.error(request, f"Error removing subject: {str(e)}")

    context = {
        'class_instance': class_instance,
        'class_subject': class_subject,
        'page_title': 'Remove Subject from Class'
    }
    return render(request, 'core/class_subject_confirm_remove.html', context)


# ============ CLASS MONITOR VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def class_monitor_assign_view(request, class_id):
    """Assign class monitor."""
    school = request.school
    Class = _get_model('Class')

    class_instance = get_object_or_404(Class, id=class_id, school=school)

    # Import form lazily to avoid circular imports
    try:
        from users.forms import ClassMonitorForm
    except ImportError:
        # Fallback form if users app doesn't exist
        from django import forms
        from .forms import BaseForm

        class FallbackClassMonitorForm(BaseForm):
            """Fallback form if users.forms not available."""
            student = forms.ModelChoiceField(
                queryset=_get_model('Student', 'students').objects.none(),
                widget=forms.Select(attrs={'class': 'form-control'})
            )
            role = forms.ChoiceField(
                choices=[('head', 'Head Monitor'), ('assistant', 'Assistant Monitor')],
                widget=forms.Select(attrs={'class': 'form-control'})
            )
            responsibilities = forms.CharField(
                widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control'})
            )
            notes = forms.CharField(
                required=False,
                widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control'})
            )

            def __init__(self, *args, **kwargs):
                class_instance = kwargs.pop('class_instance', None)
                super().__init__(*args, **kwargs)
                if class_instance:
                    Student = _get_model('Student', 'students')
                    self.fields['student'].queryset = Student.objects.filter(
                        current_class=class_instance,
                        is_active=True
                    )

        ClassMonitorForm = FallbackClassMonitorForm

    if request.method == 'POST':
        form = ClassMonitorForm(request.POST, class_instance=class_instance)
        if form.is_valid():
            try:
                # Get the ClassMonitor model
                ClassMonitor = _get_model('ClassMonitor')

                # Create monitor instance manually since we don't have the form's save method
                monitor = ClassMonitor(
                    class_instance=class_instance,
                    student=form.cleaned_data['student'],
                    role=form.cleaned_data['role'],
                    responsibilities=form.cleaned_data['responsibilities'],
                    notes=form.cleaned_data.get('notes', ''),
                    assigned_by=request.user
                )
                monitor.save()

                messages.success(request, f"{monitor.student.full_name} assigned as {monitor.get_role_display()}!")
                return redirect('core:class_detail', class_id=class_instance.id)

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error assigning monitor: {e}", exc_info=True)
                messages.error(request, f"Error assigning monitor: {str(e)}")
    else:
        form = ClassMonitorForm(class_instance=class_instance)

    context = {
        'form': form,
        'class_instance': class_instance,
        'page_title': f'Assign Class Monitor for {class_instance.name}'
    }
    return render(request, 'core/class_monitor_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_monitor_remove_view(request, class_id, monitor_id):
    """Remove class monitor."""
    school = request.school
    Class = _get_model('Class')
    ClassMonitor = _get_model('ClassMonitor')

    class_instance = get_object_or_404(Class, id=class_id, school=school)
    monitor = get_object_or_404(ClassMonitor, id=monitor_id, class_instance=class_instance)

    if request.method == 'POST':
        try:
            monitor_name = monitor.student.full_name
            monitor_role = monitor.get_role_display()
            monitor.is_active = False
            monitor.end_date = timezone.now().date()
            monitor.save()

            messages.success(request, f"{monitor_name} removed as {monitor_role}!")
            return redirect('core:class_detail', class_id=class_instance.id)

        except Exception as e:
            logger.error(f"Error removing monitor: {e}", exc_info=True)
            messages.error(request, f"Error removing monitor: {str(e)}")

    context = {
        'class_instance': class_instance,
        'monitor': monitor,
        'page_title': 'Remove Class Monitor'
    }
    return render(request, 'core/class_monitor_confirm_remove.html', context)


# ============ SUBJECT VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def subject_list_view(request):
    """List all subjects for the current school."""
    school = request.school
    Subject = _get_model('Subject')

    subjects = Subject.objects.filter(school=school).order_by('category', 'name')

    # Filters
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')
    difficulty_filter = request.GET.get('difficulty', '')

    if category_filter:
        subjects = subjects.filter(category=category_filter)

    if difficulty_filter:
        subjects = subjects.filter(difficulty_level=difficulty_filter)

    if search_query:
        subjects = subjects.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(description__icontains=search_query)
        )

    context = {
        'subjects': subjects,
        'search_query': search_query,
        'category_filter': category_filter,
        'difficulty_filter': difficulty_filter,
        'subject_categories': Subject.SUBJECT_CATEGORIES,
        'difficulty_levels': Subject.DIFFICULTY_LEVELS,
    }
    return render(request, 'core/subject_list.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def subject_create_view(request):
    """Create new subject."""
    school = request.school

    if request.method == 'POST':
        form = SubjectForm(request.POST, school=school)
        if form.is_valid():
            try:
                subject = form.save(commit=False)
                subject.school = school
                subject.save()

                messages.success(request, f"Subject '{subject.name}' created successfully!")
                return redirect('core:subject_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error creating subject: {e}", exc_info=True)
                messages.error(request, f"Error creating subject: {str(e)}")
    else:
        form = SubjectForm(school=school)

    context = {'form': form, 'page_title': 'Create New Subject'}
    return render(request, 'core/subject_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def subject_edit_view(request, subject_id):
    """Edit existing subject."""
    school = request.school
    Subject = _get_model('Subject')

    subject = get_object_or_404(Subject, id=subject_id, school=school)

    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Subject '{subject.name}' updated successfully!")
                return redirect('core:subject_detail', subject_id=subject.id)

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating subject: {e}", exc_info=True)
                messages.error(request, f"Error updating subject: {str(e)}")
    else:
        form = SubjectForm(instance=subject, school=school)

    context = {
        'form': form,
        'subject': subject,
        'page_title': f'Edit Subject: {subject.name}'
    }
    return render(request, 'core/subject_form.html', context)


@login_required
@require_school_context
def subject_detail_view(request, subject_id):
    """View subject details."""
    school = request.school
    Subject = _get_model('Subject')
    ClassSubject = _get_model('ClassSubject')

    subject = get_object_or_404(Subject, id=subject_id, school=school)

    # Get classes that offer this subject
    class_subjects = ClassSubject.objects.filter(
        subject=subject
    ).select_related('class_instance', 'teacher')

    # Get teachers who can teach this subject
    Staff = _get_model('Staff', 'users')
    teachers = Staff.objects.filter(
        school=school,
        is_active=True,
        is_teaching_staff=True,
        subjects__id=subject_id
    ).distinct()

    context = {
        'subject': subject,
        'class_subjects': class_subjects,
        'teachers': teachers,
        'classes_count': class_subjects.count(),
    }
    return render(request, 'core/subject_detail.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def subject_delete_view(request, subject_id):
    """Delete subject (only if not used in classes)."""
    school = request.school
    Subject = _get_model('Subject')
    ClassSubject = _get_model('ClassSubject')

    subject = get_object_or_404(Subject, id=subject_id, school=school)

    # Check if subject is used in any classes
    if ClassSubject.objects.filter(subject=subject).exists():
        messages.error(request, f"Cannot delete subject '{subject.name}'. It is being used in classes.")
        return redirect('core:subject_list')

    if request.method == 'POST':
        try:
            subject_name = subject.name
            subject.delete()
            messages.success(request, f"Subject '{subject_name}' deleted successfully!")
            return redirect('core:subject_list')

        except Exception as e:
            logger.error(f"Error deleting subject: {e}", exc_info=True)
            messages.error(request, f"Error deleting subject: {str(e)}")

    context = {
        'subject': subject,
        'page_title': f'Delete Subject: {subject.name}'
    }
    return render(request, 'core/subject_confirm_delete.html', context)


# ============ HTMX AJAX ENDPOINTS ============

@login_required
@require_school_context
def get_classes_for_category(request, category_id):
    """HTMX endpoint to get classes for a category."""
    school = request.school
    Class = _get_model('Class')

    classes = Class.objects.filter(
        school=school,
        category_id=category_id,
        is_active=True
    ).values('id', 'name', 'current_strength', 'max_students')

    # Return HTML for HTMX or JSON for pure AJAX
    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/class_options.html', {'classes': classes})
    return JsonResponse(list(classes), safe=False)


@login_required
@require_school_context
def get_class_stats(request):
    """HTMX endpoint for class statistics."""
    school = request.school
    Class = _get_model('Class')

    total_classes = Class.objects.filter(school=school, is_active=True).count()
    total_students = Class.objects.filter(school=school, is_active=True).aggregate(
        total=Sum('current_strength')
    )['total'] or 0

    # Classes by category
    classes_by_category = Class.objects.filter(
        school=school, is_active=True
    ).values('category__name').annotate(
        count=Count('id'),
        total_students=Sum('current_strength'),
        avg_capacity=Avg(F('current_strength') * 100.0 / F('max_students'))
    )

    # Classes by type
    classes_by_type = Class.objects.filter(
        school=school, is_active=True
    ).values('class_type').annotate(
        count=Count('id')
    )

    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/class_stats.html', {
            'total_classes': total_classes,
            'total_students': total_students,
            'classes_by_category': classes_by_category,
            'classes_by_type': classes_by_type,
        })
    return JsonResponse({
        'total_classes': total_classes,
        'total_students': total_students,
        'classes_by_category': list(classes_by_category),
        'classes_by_type': list(classes_by_type),
    })


@login_required
@require_school_context
@require_role('manage_academics')
def class_bulk_actions_view(request):
    """HTMX endpoint for bulk class actions."""
    school = request.school

    if request.method == 'POST':
        action = request.POST.get('action')
        class_ids = request.POST.getlist('class_ids')

        Class = _get_model('Class')

        if not class_ids:
            messages.error(request, "No classes selected.")
            classes = Class.objects.filter(school=school, is_active=True)
            return render(request, 'core/partials/class_table.html', {'classes': classes})

        try:
            if action == 'activate':
                Class.objects.filter(id__in=class_ids, school=school).update(is_active=True)
                messages.success(request, f"{len(class_ids)} classes activated.")
            elif action == 'deactivate':
                Class.objects.filter(id__in=class_ids, school=school).update(is_active=False)
                messages.success(request, f"{len(class_ids)} classes deactivated.")
            elif action == 'update_capacity':
                new_capacity = request.POST.get('capacity')
                if new_capacity and new_capacity.isdigit():
                    new_capacity = int(new_capacity)
                    if new_capacity > 0:
                        Class.objects.filter(id__in=class_ids, school=school).update(max_students=new_capacity)
                        messages.success(request, f"Capacity updated for {len(class_ids)} classes.")
                    else:
                        messages.error(request, "Capacity must be greater than 0.")
                else:
                    messages.error(request, "Invalid capacity value.")
            else:
                messages.error(request, "Invalid action selected.")

            # Return updated class table for HTMX
            classes = Class.objects.filter(school=school).select_related('category')
            return render(request, 'core/partials/class_table.html', {'classes': classes})

        except Exception as e:
            logger.error(f"Error in bulk class actions: {e}", exc_info=True)
            messages.error(request, f"Error processing bulk actions: {str(e)}")
            classes = Class.objects.filter(school=school)
            return render(request, 'core/partials/class_table.html', {'classes': classes})

    # Handle GET requests for HTMX modal
    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/bulk_actions_modal.html')

    return JsonResponse({'error': 'Invalid request'}, status=400)


@login_required
@require_school_context
def school_overview_stats(request):
    """HTMX endpoint for principal-only school overview stats."""
    school = request.school

    # Only allow principals and academic managers
    try:
        Profile = _get_model('Profile', 'users')
        profile = Profile.objects.get(school=school, user=request.user)

        if profile.role.system_role_type != 'principal' and not profile.role.can_manage_academics:
            if request.headers.get('HX-Request'):
                return render(request, 'core/partials/access_denied.html')
            raise PermissionDenied("You don't have permission to view these statistics.")

    except Profile.DoesNotExist:
        if request.headers.get('HX-Request'):
            return render(request, 'core/partials/access_denied.html')
        raise PermissionDenied("No profile found for this school.")

    Class = _get_model('Class')
    Student = _get_model('Student', 'students')
    Staff = _get_model('Staff', 'users')

    total_students = Student.objects.filter(school=school, is_active=True).count()
    total_staff = Staff.objects.filter(school=school, is_active=True).count()
    total_classes = Class.objects.filter(school=school, is_active=True).count()

    # Classes nearing capacity
    full_classes = Class.objects.filter(
        school=school,
        is_active=True
    ).annotate(
        capacity_percentage=F('current_strength') * 100 / F('max_students')
    ).filter(
        capacity_percentage__gte=90
    ).count()

    # Recent class creations (last 30 days)
    recent_classes = Class.objects.filter(
        school=school,
        created_at__gte=timezone.now() - timedelta(days=30)
    ).count()

    # Classes without form masters
    classes_without_masters = Class.objects.filter(
        school=school,
        is_active=True,
        form_master__isnull=True
    ).count()

    return render(request, 'core/partials/school_overview_stats.html', {
        'school': school,
        'total_students': total_students,
        'total_staff': total_staff,
        'total_classes': total_classes,
        'full_classes': full_classes,
        'recent_classes': recent_classes,
        'classes_without_masters': classes_without_masters,
        'capacity_warning': full_classes > 0,
    })


# ============ ADDITIONAL HELPER VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def class_export_view(request):
    """Export class data to CSV or Excel."""
    school = request.school
    Class = _get_model('Class')

    classes = Class.objects.filter(school=school, is_active=True).select_related(
        'category', 'form_master', 'education_level'
    ).annotate(
        student_count=Count('students', filter=Q(students__is_active=True))
    )

    format_type = request.GET.get('format', 'csv')

    if format_type == 'csv':
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="classes_{school.subdomain}_{timezone.now().date()}.csv"'

        writer = csv.writer(response)
        writer.writerow(['Class Name', 'Category', 'Form Master', 'Education Level',
                         'Current Students', 'Max Students', 'Room Number', 'Status'])

        for class_instance in classes:
            writer.writerow([
                class_instance.name,
                class_instance.category.name if class_instance.category else '',
                class_instance.form_master.full_name if class_instance.form_master else '',
                class_instance.education_level.name if class_instance.education_level else '',
                class_instance.student_count,
                class_instance.max_students,
                class_instance.room_number,
                'Active' if class_instance.is_active else 'Inactive'
            ])

        return response

    elif format_type == 'excel':
        # Excel export implementation would go here
        # Requires openpyxl or similar library
        messages.info(request, "Excel export coming soon. Using CSV for now.")
        return redirect(f"{request.path}?format=csv")

    return redirect('core:class_list')
