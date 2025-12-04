from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse, HttpResponseRedirect
from django.core.paginator import Paginator
from django.db.models import Count
from core.decorators import require_role, require_school_context
from .models import (
    Student, Parent, EducationLevel, ClassGroup, AcademicTerm, Enrollment, Attendance, Score
)
from .forms import (
    StudentCreationForm, ParentCreationForm, ClassGroupForm,
    EducationLevelForm, AcademicTermForm
)
from core.models import Subject


# ===== STUDENT MANAGEMENT VIEWS =====

@login_required
def student_list_view(request):
    """List all students for the current school."""
    # Check if user has school context
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check if user has permission to manage students in this school
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to manage students.")
            return redirect('dashboard')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    students = Student.objects.filter(school=school).select_related(
        'parent', 'education_level', 'class_group'
    ).order_by('class_group', 'first_name')
    
    # Filters
    level_filter = request.GET.get('level', '')
    class_filter = request.GET.get('class_group', '')
    status_filter = request.GET.get('status', 'active')
    search_query = request.GET.get('search', '')
    
    if level_filter:
        students = students.filter(education_level_id=level_filter)
    if class_filter:
        students = students.filter(class_group_id=class_filter)
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
    class_groups = ClassGroup.objects.filter(school=school)
    
    # Pagination
    paginator = Paginator(students, 25)  # 25 students per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'students': page_obj,
        'education_levels': education_levels,
        'class_groups': class_groups,
        'search_query': search_query,
        'level_filter': level_filter,
        'class_filter': class_filter,
        'status_filter': status_filter,
        'page_obj': page_obj,
    }
    return render(request, 'students/student_list.html', context)

@login_required
def student_create_view(request):
    """Create new student."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to add students.")
            return redirect('students:student_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = StudentCreationForm(request.POST, school=school)
        if form.is_valid():
            try:
                student = form.save(commit=False)
                student.school = school
                student.save()
                
                messages.success(request, f"Student {student.full_name} created successfully!")
                return redirect('students:student_list')
                
            except Exception as e:
                messages.error(request, f"Error creating student: {str(e)}")
    else:
        form = StudentCreationForm(school=school)
    
    context = {
        'form': form,
        'page_title': 'Add New Student'
    }
    return render(request, 'students/student_form.html', context)

@login_required
def student_detail_view(request, student_id):
    """View student details."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    student = get_object_or_404(Student, id=student_id, school=school)
    
    # Get recent attendance
    recent_attendance = Attendance.objects.filter(
        student=student
    ).select_related('academic_term').order_by('-date')[:10]
    
    # Get recent scores
    recent_scores = Score.objects.filter(
        enrollment__student=student
    ).select_related('subject', 'enrollment__academic_term').order_by('-assessment_date')[:10]
    
    # Get current enrollment
    current_enrollment = Enrollment.objects.filter(
        student=student, is_active=True
    ).select_related('class_group', 'academic_term').first()
    
    context = {
        'student': student,
        'recent_attendance': recent_attendance,
        'recent_scores': recent_scores,
        'current_enrollment': current_enrollment,
    }
    return render(request, 'students/student_detail.html', context)

@login_required
def student_edit_view(request, student_id):
    """Edit student information."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    student = get_object_or_404(Student, id=student_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to edit students.")
            return redirect('students:student_detail', student_id=student.id)
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = StudentCreationForm(request.POST, instance=student, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Student {student.full_name} updated successfully!")
                return redirect('students:student_detail', student_id=student.id)
            except Exception as e:
                messages.error(request, f"Error updating student: {str(e)}")
    else:
        form = StudentCreationForm(instance=student, school=school)
    
    context = {
        'form': form,
        'student': student,
        'page_title': f'Edit Student: {student.full_name}'
    }
    return render(request, 'students/student_form.html', context)

# ===== PARENT MANAGEMENT VIEWS =====

@login_required
def parent_list_view(request):
    """List all parents for the current school."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to manage parents.")
            return redirect('dashboard')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    parents = Parent.objects.filter(school=school).prefetch_related('student_set').order_by('first_name')
    
    search_query = request.GET.get('search', '')
    if search_query:
        parents = parents.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
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
def parent_create_view(request):
    """Create new parent."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to add parents.")
            return redirect('students:parent_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = ParentCreationForm(request.POST, school=school)
        if form.is_valid():
            try:
                parent = form.save(commit=False)
                parent.school = school
                parent.save()
                
                # Create user account if requested
                if form.cleaned_data.get('create_user_account'):
                    parent.create_user_account()
                    messages.info(request, f"User account created for {parent.full_name}")
                
                messages.success(request, f"Parent {parent.full_name} created successfully!")
                return redirect('students:parent_list')
                
            except Exception as e:
                messages.error(request, f"Error creating parent: {str(e)}")
    else:
        form = ParentCreationForm(school=school)
    
    context = {
        'form': form,
        'page_title': 'Add New Parent'
    }
    return render(request, 'students/parent_form.html', context)

@login_required
def parent_detail_view(request, parent_id):
    """View parent details."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    parent = get_object_or_404(Parent, id=parent_id, school=school)
    
    children = parent.student_set.all().select_related('education_level', 'class_group')
    
    context = {
        'parent': parent,
        'children': children,
    }
    return render(request, 'students/parent_detail.html', context)

# ===== CLASS GROUP MANAGEMENT VIEWS =====

@login_required
def class_group_list_view(request):
    """List all class groups."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to manage class groups.")
            return redirect('dashboard')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    class_groups = ClassGroup.objects.filter(school=school).select_related(
        'education_level', 'class_teacher'
    ).prefetch_related('teachers', 'student_set').order_by('education_level__order', 'name')
    
    level_filter = request.GET.get('level', '')
    if level_filter:
        class_groups = class_groups.filter(education_level_id=level_filter)
    
    education_levels = EducationLevel.objects.filter(school=school)
    
    context = {
        'class_groups': class_groups,
        'education_levels': education_levels,
        'level_filter': level_filter,
    }
    return render(request, 'students/class_group_list.html', context)

@login_required
def class_group_create_view(request):
    """Create new class group."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to create class groups.")
            return redirect('students:class_group_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = ClassGroupForm(request.POST, school=school)
        if form.is_valid():
            try:
                class_group = form.save(commit=False)
                class_group.school = school
                class_group.save()
                form.save_m2m()  # Save many-to-many relationships
                
                messages.success(request, f"Class group {class_group.name} created successfully!")
                return redirect('students:class_group_list')
                
            except Exception as e:
                messages.error(request, f"Error creating class group: {str(e)}")
    else:
        form = ClassGroupForm(school=school)
    
    context = {
        'form': form,
        'page_title': 'Create Class Group'
    }
    return render(request, 'students/class_group_form.html', context)

@login_required
def class_group_detail_view(request, class_group_id):
    """View class group details."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    class_group = get_object_or_404(ClassGroup, id=class_group_id, school=school)
    
    students = class_group.student_set.filter(is_active=True).select_related('parent')
    teachers = class_group.teachers.all()
    
    context = {
        'class_group': class_group,
        'students': students,
        'teachers': teachers,
    }
    return render(request, 'students/class_group_detail.html', context)

# ===== EDUCATION LEVEL MANAGEMENT VIEWS =====

@login_required
def education_level_list_view(request):
    """List all education levels."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to manage education levels.")
            return redirect('dashboard')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    education_levels = EducationLevel.objects.filter(school=school).order_by('level', 'order')
    
    context = {
        'education_levels': education_levels,
    }
    return render(request, 'students/education_level_list.html', context)

@login_required
def education_level_create_view(request):
    """Create new education level."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to create education levels.")
            return redirect('students:education_level_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = EducationLevelForm(request.POST)
        if form.is_valid():
            try:
                education_level = form.save(commit=False)
                education_level.school = school
                education_level.save()
                
                messages.success(request, f"Education level {education_level.name} created successfully!")
                return redirect('students:education_level_list')
                
            except Exception as e:
                messages.error(request, f"Error creating education level: {str(e)}")
    else:
        form = EducationLevelForm()
    
    context = {
        'form': form,
        'page_title': 'Create Education Level'
    }
    return render(request, 'students/education_level_form.html', context)

# ===== AJAX AND UTILITY VIEWS =====

@login_required
def get_class_groups_for_level(request, level_id):
    """AJAX endpoint to get class groups for an education level."""
    if not hasattr(request, 'school') or not request.school:
        return JsonResponse({'error': 'School context required'}, status=400)
    
    school = request.school
    class_groups = ClassGroup.objects.filter(
        school=school, 
        education_level_id=level_id
    ).values('id', 'name')
    
    return JsonResponse(list(class_groups), safe=False)

@login_required
def get_students_for_class(request, class_group_id):
    """AJAX endpoint to get students for a class group."""
    if not hasattr(request, 'school') or not request.school:
        return JsonResponse({'error': 'School context required'}, status=400)
    
    school = request.school
    students = Student.objects.filter(
        school=school, 
        class_group_id=class_group_id,
        is_active=True
    ).values('id', 'first_name', 'last_name', 'admission_number')
    
    return JsonResponse(list(students), safe=False)

@login_required
def student_quick_stats(request):
    """AJAX endpoint for student statistics."""
    if not hasattr(request, 'school') or not request.school:
        return JsonResponse({'error': 'School context required'}, status=400)
    
    school = request.school
    
    total_students = Student.objects.filter(school=school).count()
    active_students = Student.objects.filter(school=school, is_active=True).count()
    total_parents = Parent.objects.filter(school=school).count()
    
    # Students by level
    students_by_level = Student.objects.filter(
        school=school, is_active=True
    ).values('education_level__name').annotate(count=models.Count('id'))
    
    return JsonResponse({
        'total_students': total_students,
        'active_students': active_students,
        'total_parents': total_parents,
        'students_by_level': list(students_by_level),
    })


# students/views.py - ADD THESE MISSING VIEWS

@login_required
def student_delete_view(request, student_id):
    """Delete student (soft delete by setting is_active=False)."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    student = get_object_or_404(Student, id=student_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to delete students.")
            return redirect('students:student_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        try:
            # Soft delete by setting is_active=False
            student.is_active = False
            student.save()
            
            messages.success(request, f"Student {student.full_name} has been deactivated successfully!")
            return redirect('students:student_list')
            
        except Exception as e:
            messages.error(request, f"Error deactivating student: {str(e)}")
            return redirect('students:student_detail', student_id=student.id)
    
    context = {
        'student': student,
        'page_title': f'Deactivate Student: {student.full_name}'
    }
    return render(request, 'students/student_confirm_delete.html', context)
    
    
@login_required
def parent_edit_view(request, parent_id):
    """Edit parent information."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    parent = get_object_or_404(Parent, id=parent_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to edit parents.")
            return redirect('students:parent_detail', parent_id=parent.id)
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = ParentCreationForm(request.POST, instance=parent, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Parent {parent.full_name} updated successfully!")
                return redirect('students:parent_detail', parent_id=parent.id)
            except Exception as e:
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
def parent_delete_view(request, parent_id):
    """Delete parent (only if they have no children)."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    parent = get_object_or_404(Parent, id=parent_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to delete parents.")
            return redirect('students:parent_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    # Check if parent has children
    children_count = parent.children.count()
    if children_count > 0:
        messages.error(request, f"Cannot delete parent {parent.full_name}. They have {children_count} child(ren) assigned. Please reassign or delete the children first.")
        return redirect('students:parent_detail', parent_id=parent.id)
    
    if request.method == 'POST':
        try:
            parent_name = parent.full_name
            parent.delete()
            
            messages.success(request, f"Parent {parent_name} has been deleted successfully!")
            return redirect('students:parent_list')
            
        except Exception as e:
            messages.error(request, f"Error deleting parent: {str(e)}")
            return redirect('students:parent_detail', parent_id=parent.id)
    
    context = {
        'parent': parent,
        'page_title': f'Delete Parent: {parent.full_name}'
    }
    return render(request, 'students/parent_confirm_delete.html', context)
    
    
@login_required
def parent_create_account_view(request, parent_id):
    """Create user account for parent."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    parent = get_object_or_404(Parent, id=parent_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to create parent accounts.")
            return redirect('students:parent_detail', parent_id=parent.id)
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        try:
            if parent.user:
                messages.warning(request, f"Parent {parent.full_name} already has a user account.")
                return redirect('students:parent_detail', parent_id=parent.id)
            
            # Create user account
            parent.create_user_account()
            
            messages.success(request, f"User account created successfully for {parent.full_name}!")
            # Send email with login credentials (to be implemented)
            
        except Exception as e:
            messages.error(request, f"Error creating user account: {str(e)}")
    
    return redirect('students:parent_detail', parent_id=parent.id)
    
    
@login_required
def class_group_edit_view(request, class_group_id):
    """Edit class group information."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    class_group = get_object_or_404(ClassGroup, id=class_group_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to edit class groups.")
            return redirect('students:class_group_detail', class_group_id=class_group.id)
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = ClassGroupForm(request.POST, instance=class_group, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Class group {class_group.name} updated successfully!")
                return redirect('students:class_group_detail', class_group_id=class_group.id)
            except Exception as e:
                messages.error(request, f"Error updating class group: {str(e)}")
    else:
        form = ClassGroupForm(instance=class_group, school=school)
    
    context = {
        'form': form,
        'class_group': class_group,
        'page_title': f'Edit Class Group: {class_group.name}'
    }
    return render(request, 'students/class_group_form.html', context)
    
    
@login_required
def class_group_delete_view(request, class_group_id):
    """Delete class group (only if empty)."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    class_group = get_object_or_404(ClassGroup, id=class_group_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to delete class groups.")
            return redirect('students:class_group_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    # Check if class group has students
    if class_group.student_count > 0:
        messages.error(request, f"Cannot delete class group {class_group.name}. It has {class_group.student_count} student(s). Please reassign students first.")
        return redirect('students:class_group_detail', class_group_id=class_group.id)
    
    if request.method == 'POST':
        try:
            class_group_name = class_group.name
            class_group.delete()
            
            messages.success(request, f"Class group {class_group_name} has been deleted successfully!")
            return redirect('students:class_group_list')
            
        except Exception as e:
            messages.error(request, f"Error deleting class group: {str(e)}")
            return redirect('students:class_group_detail', class_group_id=class_group.id)
    
    context = {
        'class_group': class_group,
        'page_title': f'Delete Class Group: {class_group.name}'
    }
    return render(request, 'students/class_group_confirm_delete.html', context)
    
    
@login_required
def education_level_edit_view(request, level_id):
    """Edit education level information."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    education_level = get_object_or_404(EducationLevel, id=level_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to edit education levels.")
            return redirect('students:education_level_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    if request.method == 'POST':
        form = EducationLevelForm(request.POST, instance=education_level)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Education level {education_level.name} updated successfully!")
                return redirect('students:education_level_list')
            except Exception as e:
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
def education_level_delete_view(request, level_id):
    """Delete education level (only if no students or classes)."""
    if not hasattr(request, 'school') or not request.school:
        messages.warning(request, "Please select a school first.")
        return redirect('users:school_list')
    
    school = request.school
    education_level = get_object_or_404(EducationLevel, id=level_id, school=school)
    
    # Check permissions
    try:
        profile = request.user.profile_set.get(school=school)
        if not profile.role.can_manage_students and 'manage_students' not in profile.role.permissions and '*' not in profile.role.permissions:
            messages.error(request, "You don't have permission to delete education levels.")
            return redirect('students:education_level_list')
    except Exception:
        messages.error(request, "No valid profile found for this school.")
        return redirect('users:school_list')
    
    # Check if level has students or class groups
    student_count = education_level.student_set.count()
    class_group_count = education_level.classgroup_set.count()
    
    if student_count > 0 or class_group_count > 0:
        messages.error(request, 
            f"Cannot delete education level {education_level.name}. "
            f"It has {student_count} student(s) and {class_group_count} class group(s). "
            "Please reassign or delete them first."
        )
        return redirect('students:education_level_list')
    
    if request.method == 'POST':
        try:
            level_name = education_level.name
            education_level.delete()
            
            messages.success(request, f"Education level {level_name} has been deleted successfully!")
            return redirect('students:education_level_list')
            
        except Exception as e:
            messages.error(request, f"Error deleting education level: {str(e)}")
            return redirect('students:education_level_list')
    
    context = {
        'education_level': education_level,
        'page_title': f'Delete Education Level: {education_level.name}'
    }
    return render(request, 'students/education_level_confirm_delete.html', context)
    
    

@login_required
def parent_dashboard_view(request):
    """Parent dashboard - focused on children and school fees."""
    # Get parent profiles across all schools
    parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')
    
    children_data = []
    total_pending = 0
    
    for profile in parent_profiles:
        parent = profile.parent_profile
        school_children = Student.objects.filter(
            parent=parent, 
            is_active=True
        ).select_related('school', 'class_group', 'education_level')
        
        for child in school_children:
            # Get pending school fees for this child
            pending_invoices = Invoice.objects.filter(
                student=child,
                status__in=['sent', 'overdue'],
                invoice_type='school_fees'
            )
            
            child_pending = sum(inv.total_amount for inv in pending_invoices)
            total_pending += child_pending
            
            children_data.append({
                'child': child,
                'school': child.school,
                'class_group': child.class_group,
                'pending_invoices': pending_invoices,
                'total_pending': child_pending,
            })
    
    # Sort by school then by child name
    children_data.sort(key=lambda x: (x['school'].name, x['child'].first_name))
    
    context = {
        'children_data': children_data,
        'total_pending': total_pending,
        'parent_count': len(parent_profiles),
    }
    return render(request, 'students/parent_dashboard.html', context)

@login_required
def parent_payment_view(request):
    """Unified payment page for Nigerian parents."""
    parent_profiles = request.user.profile_set.filter(role__system_role_type='parent')
    
    # Get all pending invoices across all schools and children
    pending_invoices = Invoice.objects.filter(
        parent__in=[p.parent_profile for p in parent_profiles],
        status__in=['sent', 'overdue']
    ).select_related('student', 'school').order_by('school__name', 'student__first_name')
    
    # Group by school for better organization
    invoices_by_school = {}
    for invoice in pending_invoices:
        school_name = invoice.school.name
        if school_name not in invoices_by_school:
            invoices_by_school[school_name] = []
        invoices_by_school[school_name].append(invoice)
    
    total_amount = sum(invoice.total_amount for invoice in pending_invoices)
    
    if request.method == 'POST':
        # Handle payment initialization
        selected_invoices = request.POST.getlist('selected_invoices')
        
        if not selected_invoices:
            messages.error(request, "Please select at least one invoice to pay.")
            return redirect('students:parent_payment')
        
        try:
            selected_invoices = Invoice.objects.filter(
                id__in=selected_invoices,
                parent__in=[p.parent_profile for p in parent_profiles]
            )
            
            if len(selected_invoices) == 1:
                # Single invoice payment
                paystack_service = PaystackService()
                payment_data = paystack_service.initialize_payment(
                    selected_invoices[0], 
                    request.user.email,
                    metadata={'invoice_ids': [selected_invoices[0].id]}
                )
                return redirect(payment_data['authorization_url'])
            else:
                # Multiple invoices - combine amounts
                total_selected = sum(inv.total_amount for inv in selected_invoices)
                # Create combined payment (implementation needed)
                messages.info(request, f"Combined payment of ₦{total_selected:,.2f} for {len(selected_invoices)} invoices.")
                # Redirect to combined payment page
                return redirect('billing:combined_payment', invoice_ids=','.join(str(i.id) for i in selected_invoices))
                
        except PaymentProcessingError as e:
            messages.error(request, str(e))
    
    context = {
        'invoices_by_school': invoices_by_school,
        'total_amount': total_amount,
        'pending_invoices': pending_invoices,
    }
    return render(request, 'students/parent_payment.html', context)
    
    
    
@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_list_view(request):
    """List all academic terms for the school."""
    school = request.school
    terms = AcademicTerm.objects.filter(school=school).order_by('-academic_year', 'start_date')
    
    context = {
        'terms': terms,
        'current_term': AcademicTerm.objects.filter(school=school, status='active').first(),
    }
    return render(request, 'students/academic_terms_list.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_create_view(request):
    """Create a new academic term."""
    school = request.school
    
    if request.method == 'POST':
        form = AcademicTermForm(request.POST, school=school)
        if form.is_valid():
            term = form.save(commit=False)
            term.school = school
            term.save()
            messages.success(request, f'Academic term "{term.name}" created successfully.')
            return redirect('students:academic_terms')
    else:
        form = AcademicTermForm(school=school)
    
    context = {'form': form}
    return render(request, 'students/academic_term_form.html', context)
    
    


@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_edit_view(request, term_id):
    """Edit an existing academic term."""
    school = request.school
    term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    
    if request.method == 'POST':
        form = AcademicTermForm(request.POST, instance=term, school=school)
        if form.is_valid():
            form.save()
            messages.success(request, f'Academic term "{term.name}" updated successfully.')
            return redirect('students:academic_term_detail', term_id=term.id)
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
    """Delete an academic term (soft delete or hard delete)."""
    school = request.school
    term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    
    if request.method == 'POST':
        term_name = term.name
        # Check if term has attendance records before deleting
        from attendance.models import StudentAttendance
        has_attendance = StudentAttendance.objects.filter(academic_term=term).exists()
        
        if has_attendance:
            messages.error(request, f'Cannot delete "{term_name}" because it has attendance records. Close the term instead.')
            return redirect('students:academic_term_detail', term_id=term.id)
        
        term.delete()
        messages.success(request, f'Academic term "{term_name}" deleted successfully.')
        return redirect('students:academic_terms')
    
    context = {'term': term}
    return render(request, 'students/academic_term_delete.html', context)




@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_detail_view(request, term_id):
    """View academic term details."""
    school = request.school
    term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    
    # Get attendance statistics for this term
    from attendance.models import StudentAttendance
    attendance_stats = StudentAttendance.objects.filter(
        academic_term=term
    ).aggregate(
        total_records=Count('id'),
        present_count=Count('id', filter=Q(status='present')),
        absent_count=Count('id', filter=Q(status='absent')),
    )
    
    context = {
        'term': term,
        'attendance_stats': attendance_stats,
        'school_days': term.get_attendance_dates() if term else [],
    }
    return render(request, 'students/academic_term_detail.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_suspend_view(request, term_id):
    """Suspend an academic term."""
    school = request.school
    term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    
    if request.method == 'POST':
        reason = request.POST.get('reason', '')
        closure_start = request.POST.get('closure_start')
        closure_end = request.POST.get('closure_end')
        
        try:
            closure_start = datetime.strptime(closure_start, '%Y-%m-%d').date() if closure_start else None
            closure_end = datetime.strptime(closure_end, '%Y-%m-%d').date() if closure_end else None
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('students:academic_term_detail', term_id=term_id)
        
        term.suspend_term(reason, closure_start, closure_end)
        messages.warning(request, f'Term "{term.name}" has been suspended.')
        return redirect('students:academic_term_detail', term_id=term_id)
    
    context = {'term': term}
    return render(request, 'students/academic_term_suspend.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_resume_view(request, term_id):
    """Resume a suspended academic term."""
    school = request.school
    term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    
    if request.method == 'POST':
        new_end_date = request.POST.get('new_end_date')
        try:
            new_end_date = datetime.strptime(new_end_date, '%Y-%m-%d').date() if new_end_date else None
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('students:academic_term_detail', term_id=term_id)
        
        term.resume_term(new_end_date)
        messages.success(request, f'Term "{term.name}" has been resumed.')
        return redirect('students:academic_term_detail', term_id=term_id)
    
    context = {'term': term}
    return render(request, 'students/academic_term_resume.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def academic_term_close_view(request, term_id):
    """Close an academic term."""
    school = request.school
    term = get_object_or_404(AcademicTerm, id=term_id, school=school)
    
    if request.method == 'POST':
        term.close_term()
        messages.success(request, f'Term "{term.name}" has been closed.')
        return redirect('students:academic_term_detail', term_id=term_id)
    
    context = {'term': term}
    return render(request, 'students/academic_term_close.html', context)