# students/views.py
"""
CLEANED STUDENT VIEWS - Using shared architecture
NO circular imports, NO ClassGroup, PROPER service usage
"""
import logging
from typing import Optional

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count
from django.core.paginator import Paginator
from django.apps import apps
from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from typing import Any

# SHARED IMPORTS
from shared.decorators.permissions import require_role
from shared.decorators.permissions import require_school_context
from shared.constants import PARENT_PHONE_FIELD, CLASS_MODEL_PATH, StatusChoices
from shared.utils import FieldMapper
from shared.models import ClassManager

logger = logging.getLogger(__name__)


# ============ HELPER FUNCTIONS ============

def _get_model(model_name: str, app_label: str = 'students'):
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


# ============ STUDENT MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_students')
def student_list_view(request):
    """List all students for the current school."""
    school = request.school

    Student = _get_model('Student')
    EducationLevel = _get_model('EducationLevel')

    students = Student.objects.filter(school=school).select_related(
        'parent', 'education_level', 'current_class'
    ).order_by('current_class', 'first_name')

    # Filters
    level_filter = request.GET.get('level', '')
    class_filter = request.GET.get('current_class', '')
    status_filter = request.GET.get('status', 'active')
    search_query = request.GET.get('search', '')

    if level_filter:
        students = students.filter(education_level_id=level_filter)

    if class_filter:
        # ✅ Use ClassManager to validate class ID
        class_id = ClassManager.prepare_class_data({'class': class_filter}).get('current_class_id')
        if class_id:
            students = students.filter(current_class_id=class_id)

    if status_filter == 'active':
        students = students.filter(is_active=True)
    elif status_filter == 'inactive':
        students = students.filter(is_active=False)

    if search_query:
        students = students.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(admission_number__icontains=search_query) |
            Q(parent__first_name__icontains=search_query) |
            Q(parent__last_name__icontains=search_query)
        )

    education_levels = EducationLevel.objects.filter(school=school)

    # Get class choices using ClassManager
    class_choices = ClassManager.get_class_choices(school)

    # Pagination
    paginator = Paginator(students, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'students': page_obj,
        'education_levels': education_levels,
        'class_choices': class_choices,  # ✅ Use core.Class choices
        'search_query': search_query,
        'level_filter': level_filter,
        'class_filter': class_filter,
        'status_filter': status_filter,
        'page_obj': page_obj,
    }
    return render(request, 'students/student_list.html', context)


@login_required
@require_school_context
@require_role('manage_students')
def student_create_view(request):
    """Create new student."""
    school = request.school

    # Import forms lazily to avoid circular imports
    from .forms import StudentCreationForm

    if request.method == 'POST':
        # Use FieldMapper to standardize form data
        form_data = FieldMapper.map_form_to_model(request.POST, 'student')
        form = StudentCreationForm(form_data, school=school)

        if form.is_valid():
            try:
                # ✅ Use ClassManager to validate class availability
                class_id = form.cleaned_data.get('current_class_id')
                if class_id:
                    is_available, message, class_instance = ClassManager.validate_class_availability(
                        class_id, school, is_staff=form.cleaned_data.get('is_staff_child', False)
                    )

                    if not is_available:
                        messages.error(request, message)
                        return render(request, 'students/student_form.html', {'form': form})

                student = form.save(commit=False)
                student.school = school
                student.save()

                # ✅ Use service for post-creation logic
                from .services import StudentService
                StudentService.handle_student_creation(student, request.user)

                messages.success(request, f"Student {student.full_name} created successfully!")
                return redirect('students:student_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error creating student: {e}", exc_info=True)
                messages.error(request, f"Error creating student: {str(e)}")
    else:
        form = StudentCreationForm(school=school)

    context = {
        'form': form,
        'page_title': 'Add New Student'
    }
    return render(request, 'students/student_form.html', context)


@login_required
@require_school_context
def student_detail_view(request, student_id):
    """View student details."""
    school = request.school
    Student = _get_model('Student')

    student = get_object_or_404(Student, id=student_id, school=school)

    # Check if user has permission to view this student
    try:
        Profile = _get_model('Profile', 'users')
        profile = Profile.objects.get(user=request.user, school=school)

        # Teachers can only view students in their classes
        if profile.role.system_role_type == 'teacher':
            # Check if student is in teacher's classes
            if hasattr(request.user, 'staff'):
                teacher_classes = request.user.staff.classes_teaching.all()
                if student.current_class not in teacher_classes:
                    raise PermissionDenied("You don't have permission to view this student.")

    except Profile.DoesNotExist:
        raise PermissionDenied("No profile found for this school.")

    # Get recent attendance
    Attendance = _get_model('Attendance')
    recent_attendance = Attendance.objects.filter(
        student=student
    ).select_related('academic_term').order_by('-date')[:10]

    # Get recent scores
    Score = _get_model('Score')
    recent_scores = Score.objects.filter(
        enrollment__student=student
    ).select_related('subject', 'enrollment__academic_term').order_by('-assessment_date')[:10]

    # Get current enrollment
    Enrollment = _get_model('Enrollment')
    current_enrollment = Enrollment.objects.filter(
        student=student, is_active=True
    ).select_related('academic_term').first()

    context = {
        'student': student,
        'recent_attendance': recent_attendance,
        'recent_scores': recent_scores,
        'current_enrollment': current_enrollment,
    }
    return render(request, 'students/student_detail.html', context)


@login_required
@require_school_context
@require_role('manage_students')
def student_edit_view(request, student_id):
    """Edit student information."""
    school = request.school
    Student = _get_model('Student')

    student = get_object_or_404(Student, id=student_id, school=school)

    from .forms import StudentCreationForm

    if request.method == 'POST':
        form_data = FieldMapper.map_form_to_model(request.POST, 'student')
        form = StudentCreationForm(form_data, instance=student, school=school)

        if form.is_valid():
            try:
                # Check class capacity if changing classes
                old_class_id = student.current_class_id if student.current_class else None
                new_class_id = form.cleaned_data.get('current_class_id')

                if new_class_id and new_class_id != old_class_id:
                    is_available, message, class_instance = ClassManager.validate_class_availability(
                        new_class_id, school, is_staff=form.cleaned_data.get('is_staff_child', False)
                    )

                    if not is_available:
                        messages.error(request, message)
                        return render(request, 'students/student_form.html', {
                            'form': form,
                            'student': student
                        })

                form.save()
                messages.success(request, f"Student {student.full_name} updated successfully!")
                return redirect('students:student_detail', student_id=student.id)

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating student: {e}", exc_info=True)
                messages.error(request, f"Error updating student: {str(e)}")
    else:
        form = StudentCreationForm(instance=student, school=school)

    context = {
        'form': form,
        'student': student,
        'page_title': f'Edit Student: {student.full_name}'
    }
    return render(request, 'students/student_form.html', context)


@login_required
@require_school_context
@require_role('manage_students')
def student_delete_view(request, student_id):
    """Delete student (soft delete by setting is_active=False)."""
    school = request.school
    Student = _get_model('Student')

    student = get_object_or_404(Student, id=student_id, school=school)

    if request.method == 'POST':
        try:
            # Soft delete by setting is_active=False
            student.is_active = False
            student.save()

            # ✅ Use service for post-deletion logic
            from .services import StudentService
            StudentService.handle_student_deactivation(student, request.user)

            messages.success(request, f"Student {student.full_name} has been deactivated successfully!")
            return redirect('students:student_list')

        except Exception as e:
            logger.error(f"Error deactivating student: {e}", exc_info=True)
            messages.error(request, f"Error deactivating student: {str(e)}")
            return redirect('students:student_detail', student_id=student.id)

    context = {
        'student': student,
        'page_title': f'Deactivate Student: {student.full_name}'
    }
    return render(request, 'students/student_confirm_delete.html', context)


# ============ PARENT MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_students')
def parent_list_view(request):
    """List all parents for the current school."""
    school = request.school
    Parent = _get_model('Parent')

    parents = Parent.objects.filter(school=school).prefetch_related('student_set').order_by('first_name')

    search_query = request.GET.get('search', '')
    if search_query:
        parents = parents.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(PARENT_PHONE_FIELD + '__icontains', search_query)  # ✅ Use shared constant
        )

    # Pagination
    paginator = Paginator(parents, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'parents': page_obj,
        'search_query': search_query,
        'page_obj': page_obj,
    }
    return render(request, 'students/parent_list.html', context)


@login_required
@require_school_context
@require_role('manage_students')
def parent_create_view(request):
    """Create new parent."""
    school = request.school

    from .forms import ParentCreationForm

    if request.method == 'POST':
        form_data = FieldMapper.map_form_to_model(request.POST, 'parent')
        form = ParentCreationForm(form_data, school=school)

        if form.is_valid():
            try:
                parent = form.save(commit=False)
                parent.school = school
                parent.save()

                # Create user account if requested (through service)
                if form.cleaned_data.get('create_user_account'):
                    from .services import ParentService
                    ParentService.create_parent_user_account(parent, request.user)
                    messages.info(request, f"User account created for {parent.full_name}")

                messages.success(request, f"Parent {parent.full_name} created successfully!")
                return redirect('students:parent_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error creating parent: {e}", exc_info=True)
                messages.error(request, f"Error creating parent: {str(e)}")
    else:
        form = ParentCreationForm(school=school)

    context = {
        'form': form,
        'page_title': 'Add New Parent'
    }
    return render(request, 'students/parent_form.html', context)


@login_required
@require_school_context
def parent_detail_view(request, parent_id):
    """View parent details."""
    school = request.school
    Parent = _get_model('Parent')
    Student = _get_model('Student')

    parent = get_object_or_404(Parent, id=parent_id, school=school)

    # Check if user has permission
    try:
        Profile = _get_model('Profile', 'users')
        profile = Profile.objects.get(user=request.user, school=school)

        # Parents can only view their own details
        if profile.role.system_role_type == 'parent' and profile.parent_profile != parent:
            raise PermissionDenied("You can only view your own profile.")

    except Profile.DoesNotExist:
        raise PermissionDenied("No profile found for this school.")

    children = parent.student_set.all().select_related('education_level', 'current_class')

    context = {
        'parent': parent,
        'children': children,
    }
    return render(request, 'students/parent_detail.html', context)


@login_required
@require_school_context
@require_role('manage_students')
def parent_edit_view(request, parent_id):
    """Edit parent information."""
    school = request.school
    Parent = _get_model('Parent')

    parent = get_object_or_404(Parent, id=parent_id, school=school)

    from .forms import ParentCreationForm

    if request.method == 'POST':
        form_data = FieldMapper.map_form_to_model(request.POST, 'parent')
        form = ParentCreationForm(form_data, instance=parent, school=school)

        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Parent {parent.full_name} updated successfully!")
                return redirect('students:parent_detail', parent_id=parent.id)
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating parent: {e}", exc_info=True)
                messages.error(request, f"Error updating parent: {str(e)}")
    else:
        form = ParentCreationForm(instance=parent, school=school)

    context = {
        'form': form,
        'parent': parent,
        'page_title': f'Edit Parent: {parent.full_name}'
    }
    return render(request, 'students/parent_form.html', context)


@login_required
@require_school_context
@require_role('manage_students')
def parent_delete_view(request, parent_id):
    """Delete parent (only if they have no children)."""
    school = request.school
    Parent = _get_model('Parent')

    parent = get_object_or_404(Parent, id=parent_id, school=school)

    # Check if parent has children
    children_count = parent.children.count()
    if children_count > 0:
        messages.error(request, f"Cannot delete parent {parent.full_name}. They have {children_count} child(ren) assigned.")
        return redirect('students:parent_detail', parent_id=parent.id)

    if request.method == 'POST':
        try:
            parent_name = parent.full_name
            parent.delete()

            messages.success(request, f"Parent {parent_name} has been deleted successfully!")
            return redirect('students:parent_list')

        except Exception as e:
            logger.error(f"Error deleting parent: {e}", exc_info=True)
            messages.error(request, f"Error deleting parent: {str(e)}")
            return redirect('students:parent_detail', parent_id=parent.id)

    context = {
        'parent': parent,
        'page_title': f'Delete Parent: {parent.full_name}'
    }
    return render(request, 'students/parent_confirm_delete.html', context)


# ============ EDUCATION LEVEL MANAGEMENT VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def education_level_list_view(request):
    """List all education levels."""
    school = request.school
    EducationLevel = _get_model('EducationLevel')

    education_levels = EducationLevel.objects.filter(school=school).order_by('level', 'order')

    context = {
        'education_levels': education_levels,
    }
    return render(request, 'students/education_level_list.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def education_level_create_view(request):
    """Create new education level."""
    school = request.school

    from .forms import EducationLevelForm

    if request.method == 'POST':
        form = EducationLevelForm(request.POST)
        if form.is_valid():
            try:
                education_level = form.save(commit=False)
                education_level.school = school
                education_level.save()

                messages.success(request, f"Education level {education_level.name} created successfully!")
                return redirect('students:education_level_list')

            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error creating education level: {e}", exc_info=True)
                messages.error(request, f"Error creating education level: {str(e)}")
    else:
        form = EducationLevelForm()

    context = {
        'form': form,
        'page_title': 'Create Education Level'
    }
    return render(request, 'students/education_level_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def education_level_edit_view(request, level_id):
    """Edit education level information."""
    school = request.school
    EducationLevel = _get_model('EducationLevel')

    education_level = get_object_or_404(EducationLevel, id=level_id, school=school)

    from .forms import EducationLevelForm

    if request.method == 'POST':
        form = EducationLevelForm(request.POST, instance=education_level)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Education level {education_level.name} updated successfully!")
                return redirect('students:education_level_list')
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating education level: {e}", exc_info=True)
                messages.error(request, f"Error updating education level: {str(e)}")
    else:
        form = EducationLevelForm(instance=education_level)

    context = {
        'form': form,
        'education_level': education_level,
        'page_title': f'Edit Education Level: {education_level.name}'
    }
    return render(request, 'students/education_level_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def education_level_delete_view(request, level_id):
    """Delete education level (only if no students or classes)."""
    school = request.school
    EducationLevel = _get_model('EducationLevel')

    education_level = get_object_or_404(EducationLevel, id=level_id, school=school)

    # Check if level has students
    student_count = education_level.student_set.count()

    # Check if level has classes (core.Class)
    Class = _get_model('Class', 'core')
    class_count = Class.objects.filter(education_level=education_level).count()

    if student_count > 0 or class_count > 0:
        messages.error(request,
            f"Cannot delete education level {education_level.name}. "
            f"It has {student_count} student(s) and {class_count} class(es)."
        )
        return redirect('students:education_level_list')

    if request.method == 'POST':
        try:
            level_name = education_level.name
            education_level.delete()

            messages.success(request, f"Education level {level_name} has been deleted successfully!")
            return redirect('students:education_level_list')

        except Exception as e:
            logger.error(f"Error deleting education level: {e}", exc_info=True)
            messages.error(request, f"Error deleting education level: {str(e)}")
            return redirect('students:education_level_list')

    context = {
        'education_level': education_level,
        'page_title': f'Delete Education Level: {education_level.name}'
    }
    return render(request, 'students/education_level_confirm_delete.html', context)


# ============ AJAX AND UTILITY VIEWS ============

@login_required
@require_school_context
def get_classes_for_level(request, level_id):
    """AJAX endpoint to get classes for an education level."""
    school = request.school
    Class = _get_model('Class', 'core')

    classes = Class.objects.filter(
        school=school,
        education_level_id=level_id,
        is_active=True
    ).values('id', 'name')

    return JsonResponse(list(classes), safe=False)


@login_required
@require_school_context
def get_students_for_class(request, class_id):
    """AJAX endpoint to get students for a class."""
    school = request.school
    Student = _get_model('Student')

    students = Student.objects.filter(
        school=school,
        current_class_id=class_id,  # ✅ Use current_class instead of class_group
        is_active=True
    ).values('id', 'first_name', 'last_name', 'admission_number')

    return JsonResponse(list(students), safe=False)


@login_required
@require_school_context
def student_quick_stats(request):
    """AJAX endpoint for student statistics."""
    school = request.school
    Student = _get_model('Student')

    stats = {
        'total': Student.objects.filter(school=school).count(),
        'active': Student.objects.filter(school=school, is_active=True).count(),
        'staff_children': Student.objects.filter(school=school, is_staff_child=True).count(),
        'by_gender': {
            'male': Student.objects.filter(school=school, gender='M').count(),
            'female': Student.objects.filter(school=school, gender='F').count(),
        }
    }

    return JsonResponse(stats)


# ============ ACADEMIC TERM VIEWS ============

@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_list_view(request):
    """List all academic terms for the school."""
    school = request.school
    AcademicTerm = _get_model('AcademicTerm')

    terms = AcademicTerm.objects.filter(school=school).order_by('-academic_year', 'start_date')
    current_term = AcademicTerm.objects.filter(school=school, status='active').first()

    context = {
        'terms': terms,
        'current_term': current_term,
    }
    return render(request, 'students/academic_terms_list.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_create_view(request):
    """Create a new academic term."""
    school = request.school

    from .forms import AcademicTermForm

    if request.method == 'POST':
        form = AcademicTermForm(request.POST, school=school)
        if form.is_valid():
            try:
                term = form.save(commit=False)
                term.school = school
                term.save()
                messages.success(request, f'Academic term "{term.name}" created successfully.')
                return redirect('students:academic_terms')
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error creating academic term: {e}", exc_info=True)
                messages.error(request, f"Error creating academic term: {str(e)}")
    else:
        form = AcademicTermForm(school=school)

    context = {'form': form}
    return render(request, 'students/academic_term_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_detail_view(request, term_id):
    """View academic term details."""
    school = request.school
    AcademicTerm = _get_model('AcademicTerm')

    term = get_object_or_404(AcademicTerm, id=term_id, school=school)

    # Get attendance statistics for this term
    Attendance = _get_model('Attendance')
    attendance_stats = Attendance.objects.filter(
        academic_term=term
    ).aggregate(
        total_records=Count('id'),
        present_count=Count('id', filter=Q(status='present')),
        absent_count=Count('id', filter=Q(status='absent')),
    )

    context = {
        'term': term,
        'attendance_stats': attendance_stats,
    }
    return render(request, 'students/academic_term_detail.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_edit_view(request, term_id):
    """Edit an existing academic term."""
    school = request.school
    AcademicTerm = _get_model('AcademicTerm')

    term = get_object_or_404(AcademicTerm, id=term_id, school=school)

    from .forms import AcademicTermForm

    if request.method == 'POST':
        form = AcademicTermForm(request.POST, instance=term, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f'Academic term "{term.name}" updated successfully.')
                return redirect('students:academic_term_detail', term_id=term.id)
            except ValidationError as e:
                for field, errors in e.message_dict.items():
                    for error in errors:
                        messages.error(request, f"{field}: {error}")
            except Exception as e:
                logger.error(f"Error updating academic term: {e}", exc_info=True)
                messages.error(request, f"Error updating academic term: {str(e)}")
    else:
        form = AcademicTermForm(instance=term, school=school)

    context = {
        'form': form,
        'term': term,
        'title': f'Edit {term.name}'
    }
    return render(request, 'students/academic_term_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_delete_view(request, term_id):
    """Delete an academic term."""
    school = request.school
    AcademicTerm = _get_model('AcademicTerm')

    term = get_object_or_404(AcademicTerm, id=term_id, school=school)

    if request.method == 'POST':
        try:
            # Check if term has attendance records
            Attendance = _get_model('Attendance')
            has_attendance = Attendance.objects.filter(academic_term=term).exists()

            if has_attendance:
                messages.error(request, f'Cannot delete "{term.name}" because it has attendance records.')
                return redirect('students:academic_term_detail', term_id=term.id)

            term_name = term.name
            term.delete()
            messages.success(request, f'Academic term "{term_name}" deleted successfully.')
            return redirect('students:academic_terms')

        except Exception as e:
            logger.error(f"Error deleting academic term: {e}", exc_info=True)
            messages.error(request, f"Error deleting academic term: {str(e)}")
            return redirect('students:academic_term_detail', term_id=term.id)

    context = {'term': term}
    return render(request, 'students/academic_term_delete.html', context)
