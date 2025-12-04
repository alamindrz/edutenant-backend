# core/views.py 
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy
from core.decorators import require_role, require_school_context
from .models import Subject, Class, ClassCategory
from .forms import SubjectForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from django.http import JsonResponse
from django.core.paginator import Paginator

from core.decorators import require_role, require_school_context
from .models import Class, ClassCategory, ClassSubject, Subject, ClassMonitor
from .forms import ClassForm, ClassCategoryForm, ClassSubjectForm
from django.db import models
from django.utils import timezone
from datetime import timedelta  
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from django.db.models import Count





@require_http_methods(["POST"])
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

# ===== CLASS CATEGORY VIEWS =====

@login_required
@require_school_context
@require_role('manage_academics')
def class_category_list_view(request):
    """List all class categories for the current school."""
    school = request.school
    
    categories = ClassCategory.objects.filter(school=school).annotate(
        class_count=Count('class', filter=Q(class__is_active=True))
    ).order_by('display_order', 'name')
    
    context = {
        'categories': categories,
    }
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
                
            except Exception as e:
                messages.error(request, f"Error creating class category: {str(e)}")
    else:
        form = ClassCategoryForm()
    
    context = {
        'form': form,
        'page_title': 'Create Class Category'
    }
    return render(request, 'core/class_category_form.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def class_category_edit_view(request, category_id):
    """Edit existing class category."""
    school = request.school
    category = get_object_or_404(ClassCategory, id=category_id, school=school)
    
    if request.method == 'POST':
        form = ClassCategoryForm(request.POST, instance=category)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Class category '{category.name}' updated successfully!")
                return redirect('core:class_category_list')
            except Exception as e:
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
    category = get_object_or_404(ClassCategory, id=category_id, school=school)
    
    # Check if category has classes
    if category.class_set.exists():
        messages.error(request, f"Cannot delete category '{category.name}'. It contains classes.")
        return redirect('core:class_category_list')
    
    if request.method == 'POST':
        try:
            category_name = category.name
            category.delete()
            messages.success(request, f"Class category '{category_name}' deleted successfully!")
            return redirect('core:class_category_list')
        except Exception as e:
            messages.error(request, f"Error deleting class category: {str(e)}")
    
    context = {
        'category': category,
        'page_title': f'Delete Class Category: {category.name}'
    }
    return render(request, 'core/class_category_confirm_delete.html', context)

# ===== CLASS VIEWS =====
@login_required
@require_school_context
@require_role('manage_academics')



@login_required
@require_school_context
@require_role('manage_academics')
def class_list_view(request):
    """List all classes for the current school."""
    school = request.school
    
    # ✅ FIXED: Now using the correct reverse relationship 'students'
    classes = Class.objects.filter(school=school, is_active=True).select_related(
        'category', 'form_master', 'assistant_form_master'
    ).annotate(
        student_count=Count('students', filter=Q(students__is_active=True, students__admission_status='enrolled'))
    ).order_by('category__display_order', 'name')
    
    # Filters
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', 'active')
    
    if category_filter:
        classes = classes.filter(category_id=category_filter)
    
    if status_filter == 'inactive':
        classes = classes.filter(is_active=False)
    elif status_filter == 'all':
        classes = Class.objects.filter(school=school)
    else:
        classes = classes.filter(is_active=True)
    
    if search_query:
        classes = classes.filter(
            Q(name__icontains=search_query) |
            Q(code__icontains=search_query) |
            Q(room_number__icontains=search_query) |
            Q(form_master__first_name__icontains=search_query) |
            Q(form_master__last_name__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )
    
    categories = ClassCategory.objects.filter(school=school)
    
    # Return partial for HTMX requests
    if request.headers.get('HX-Request'):
        template = 'core/partials/class_table.html'
    else:
        template = 'core/class_list.html'
    
    context = {
        'classes': classes,
        'categories': categories,
        'search_query': search_query,
        'category_filter': category_filter,
        'status_filter': status_filter,
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
                
                messages.success(request, f"Class '{class_instance.name}' created successfully!")
                return redirect('core:class_list')
                
            except Exception as e:
                messages.error(request, f"Error creating class: {str(e)}")
    else:
        form = ClassForm(school=school)
    
    context = {
        'form': form,
        'page_title': 'Create New Class'
    }
    return render(request, 'core/class_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def class_update_view(request, pk):
    """Update existing class."""
    school = request.school
    
    # Get the class instance, ensuring it belongs to the current school
    class_instance = get_object_or_404(Class, pk=pk, school=school)
    
    if request.method == 'POST':
        form = ClassForm(request.POST, instance=class_instance, school=school)
        if form.is_valid():
            try:
                class_instance = form.save()
                
                # Update class strength after saving
                class_instance.update_strength()
                class_instance.save()  # Save again to update current_strength
                
                messages.success(request, f"Class '{class_instance.name}' updated successfully!")
                
                # Return to class detail if HTMX request
                if request.headers.get('HX-Request'):
                    return redirect('core:class_detail', pk=class_instance.pk)
                else:
                    return redirect('core:class_list')
                    
            except Exception as e:
                messages.error(request, f"Error updating class: {str(e)}")
    else:
        form = ClassForm(instance=class_instance, school=school)
    
    context = {
        'form': form,
        'class_instance': class_instance,
        'page_title': f'Update {class_instance.name}',
        'submit_text': 'Update Class',
        'cancel_url': request.META.get('HTTP_REFERER', reverse_lazy('core:class_detail', kwargs={'pk': class_instance.pk}))
    }
    return render(request, 'core/class_form.html', context)



@login_required
@require_school_context
@require_role('manage_academics')
def class_detail_view(request, class_id):
    """View class details."""
    school = request.school
    class_instance = get_object_or_404(Class, id=class_id, school=school)
    
    # Get class subjects
    class_subjects = ClassSubject.objects.filter(class_instance=class_instance).select_related('subject', 'teacher')
    
    # Get class monitors
    class_monitors = ClassMonitor.objects.filter(class_instance=class_instance, is_active=True).select_related('student')
    
    # Get students in this class
    from students.models import Student
    students = Student.objects.filter(current_class=class_instance, is_active=True).select_related('parent')
    
    context = {
        'class_instance': class_instance,
        'class_subjects': class_subjects,
        'class_monitors': class_monitors,
        'students': students,
    }
    return render(request, 'core/class_detail.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def class_edit_view(request, class_id):
    """Edit existing class."""
    school = request.school
    class_instance = get_object_or_404(Class, id=class_id, school=school)
    
    if request.method == 'POST':
        form = ClassForm(request.POST, instance=class_instance, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Class '{class_instance.name}' updated successfully!")
                return redirect('core:class_detail', class_id=class_instance.id)
            except Exception as e:
                messages.error(request, f"Error updating class: {str(e)}")
    else:
        form = ClassForm(instance=class_instance, school=school)
    
    context = {
        'form': form,
        'class_instance': class_instance,
        'page_title': f'Edit Class: {class_instance.name}'
    }
    return render(request, 'core/class_form.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def class_delete_view(request, class_id):
    """Delete class (soft delete)."""
    school = request.school
    class_instance = get_object_or_404(Class, id=class_id, school=school)
    
    # Check if class has students
    if class_instance.students.exists():
        messages.error(request, f"Cannot delete class '{class_instance.name}'. It has students assigned.")
        return redirect('core:class_detail', class_id=class_instance.id)
    
    if request.method == 'POST':
        try:
            class_instance.is_active = False
            class_instance.save()
            messages.success(request, f"Class '{class_instance.name}' deleted successfully!")
            return redirect('core:class_list')
        except Exception as e:
            messages.error(request, f"Error deleting class: {str(e)}")
    
    context = {
        'class_instance': class_instance,
        'page_title': f'Delete Class: {class_instance.name}'
    }
    return render(request, 'core/class_confirm_delete.html', context)

# ===== CLASS SUBJECT VIEWS =====

@login_required
@require_school_context
@require_role('manage_academics')
def class_subject_add_view(request, class_id):
    """Add subject to class."""
    school = request.school
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
                
            except Exception as e:
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
@require_role('manage_academics')  # This should now work with the fixed decorator
def class_subject_edit_view(request, class_id, subject_id):
    """Edit class subject assignment."""
    school = request.school
    class_instance = get_object_or_404(Class, id=class_id, school=school)
    class_subject = get_object_or_404(ClassSubject, class_instance=class_instance, id=subject_id)
    
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, instance=class_subject, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Subject assignment updated successfully!")
                return redirect('core:class_detail', class_id=class_instance.id)
            except Exception as e:
                messages.error(request, f"Error updating subject assignment: {str(e)}")
    else:
        form = ClassSubjectForm(instance=class_subject, school=school)
    
    context = {
        'form': form,
        'class_instance': class_instance,
        'class_subject': class_subject,
        'page_title': f'Edit Subject Assignment'
    }
    return render(request, 'core/class_subject_form.html', context)





@login_required
@require_school_context
@require_role('manage_academics')
def class_subject_remove_view(request, class_id, subject_id):
    """Remove subject from class."""
    school = request.school
    class_instance = get_object_or_404(Class, id=class_id, school=school)
    class_subject = get_object_or_404(ClassSubject, class_instance=class_instance, id=subject_id)
    
    if request.method == 'POST':
        try:
            subject_name = class_subject.subject.name
            class_subject.delete()
            messages.success(request, f"Subject '{subject_name}' removed from class!")
            return redirect('core:class_detail', class_id=class_instance.id)
        except Exception as e:
            messages.error(request, f"Error removing subject: {str(e)}")
    
    context = {
        'class_instance': class_instance,
        'class_subject': class_subject,
        'page_title': f'Remove Subject from Class'
    }
    return render(request, 'core/class_subject_confirm_remove.html', context)

# ===== CLASS MONITOR VIEWS =====

@login_required
@require_school_context
@require_role('manage_academics')
def class_monitor_assign_view(request, class_id):
    """Assign class monitor."""
    school = request.school
    class_instance = get_object_or_404(Class, id=class_id, school=school)
    
    from students.models import Student
    from users.forms import ClassMonitorForm
    
    if request.method == 'POST':
        form = ClassMonitorForm(request.POST, class_instance=class_instance)
        if form.is_valid():
            try:
                monitor = form.save(commit=False)
                monitor.class_instance = class_instance
                monitor.assigned_by = request.user
                monitor.save()
                
                messages.success(request, f"{monitor.student.full_name} assigned as {monitor.get_role_display()}!")
                return redirect('core:class_detail', class_id=class_instance.id)
                
            except Exception as e:
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
            messages.error(request, f"Error removing monitor: {str(e)}")
    
    context = {
        'class_instance': class_instance,
        'monitor': monitor,
        'page_title': f'Remove Class Monitor'
    }
    return render(request, 'core/class_monitor_confirm_remove.html', context)

# ===== HTMX AJAX ENDPOINTS =====
@login_required
@require_school_context
def get_classes_for_category(request, category_id):
    """HTMX endpoint to get classes for a category."""
    school = request.school
    classes = Class.objects.filter(
        school=school, 
        category_id=category_id,
        is_active=True
    ).values('id', 'name', 'current_strength', 'max_students')
    
    # Return HTML for HTMX or JSON for pure AJAX
    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/class_options.html', {
            'classes': classes
        })
    else:
        return JsonResponse(list(classes), safe=False)

@login_required
@require_school_context
def get_class_stats(request):
    """HTMX endpoint for class statistics."""
    school = request.school
    
    total_classes = Class.objects.filter(school=school, is_active=True).count()
    total_students = Class.objects.filter(school=school, is_active=True).aggregate(
        total=Sum('current_strength')
    )['total'] or 0
    
    # Classes by category
    classes_by_category = Class.objects.filter(
        school=school, is_active=True
    ).values('category__name').annotate(
        count=Count('id'),
        total_students=Sum('current_strength')
    )
    
    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/class_stats.html', {
            'total_classes': total_classes,
            'total_students': total_students,
            'classes_by_category': classes_by_category,
        })
    else:
        return JsonResponse({
            'total_classes': total_classes,
            'total_students': total_students,
            'classes_by_category': list(classes_by_category),
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
        
        if action == 'activate':
            Class.objects.filter(id__in=class_ids, school=school).update(is_active=True)
            messages.success(request, f"{len(class_ids)} classes activated.")
        elif action == 'deactivate':
            Class.objects.filter(id__in=class_ids, school=school).update(is_active=False)
            messages.success(request, f"{len(class_ids)} classes deactivated.")
        elif action == 'update_capacity':
            new_capacity = request.POST.get('capacity')
            if new_capacity:
                Class.objects.filter(id__in=class_ids, school=school).update(max_students=new_capacity)
                messages.success(request, f"Capacity updated for {len(class_ids)} classes.")
        
        # Return updated class table for HTMX
        classes = Class.objects.filter(school=school, is_active=True)
        return render(request, 'core/partials/class_table.html', {
            'classes': classes
        })
    
    # Handle GET requests for HTMX
    if request.headers.get('HX-Request'):
        return render(request, 'core/partials/bulk_actions_modal.html')
    
    return JsonResponse({'error': 'Invalid request'}, status=400)






@login_required
@require_school_context
@require_role('manage_academics')
def subject_list_view(request):
    """List all subjects for the current school."""
    school = request.school
    
    subjects = Subject.objects.filter(school=school).order_by('category', 'name')
    
    # Filters
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')
    
    if category_filter:
        subjects = subjects.filter(category=category_filter)
    
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
        'subject_categories': Subject.SUBJECT_CATEGORIES,
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
                
            except Exception as e:
                messages.error(request, f"Error creating subject: {str(e)}")
    else:
        form = SubjectForm(school=school)
    
    context = {
        'form': form,
        'page_title': 'Create New Subject'
    }
    return render(request, 'core/subject_form.html', context)


@login_required
@require_school_context
@require_role('manage_academics')
def subject_edit_view(request, subject_id):
    """Edit existing subject."""
    school = request.school
    subject = get_object_or_404(Subject, id=subject_id, school=school)
    
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subject, school=school)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Subject '{subject.name}' updated successfully!")
                # ✅ FIX: Use subject_id, not subject.pk or other variations
                return redirect('core:subject_detail', subject_id=subject.id)
            except Exception as e:
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
@require_role('manage_academics')
def subject_detail_view(request, subject_id):
    """View subject details."""
    school = request.school
    subject = get_object_or_404(Subject, id=subject_id, school=school)
    
    # Get classes that offer this subject
    from core.models import ClassSubject
    class_subjects = ClassSubject.objects.filter(subject=subject).select_related('class_instance')
    
    context = {
        'subject': subject,
        'class_subjects': class_subjects,
    }
    return render(request, 'core/subject_detail.html', context)

@login_required
@require_school_context
@require_role('manage_academics')
def subject_delete_view(request, subject_id):
    """Delete subject (only if not used in classes)."""
    school = request.school
    subject = get_object_or_404(Subject, id=subject_id, school=school)
    
    # Check if subject is used in any classes
    from core.models import ClassSubject
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
            messages.error(request, f"Error deleting subject: {str(e)}")
    
    context = {
        'subject': subject,
        'page_title': f'Delete Subject: {subject.name}'
    }
    return render(request, 'core/subject_confirm_delete.html', context)
    
    
@login_required
@require_school_context
def school_overview_stats(request):
    """HTMX endpoint for principal-only school overview stats."""
    school = request.school
    
    # Only allow principals
    profile = request.user.profile_set.get(school=school)
    if profile.role.system_role_type != 'principal' and not profile.role.can_manage_academics:
        return render(request, 'core/partials/access_denied.html')
    
    from students.models import Student
    from users.models import Staff
    
    total_students = Student.objects.filter(school=school, is_active=True).count()
    total_staff = Staff.objects.filter(school=school, is_active=True).count()
    total_classes = Class.objects.filter(school=school, is_active=True).count()
    
    # Classes nearing capacity - FIXED
    full_classes = Class.objects.filter(
        school=school, 
        is_active=True,
        current_strength__gte=models.F('max_students') - 5
    ).count()
    
    # Recent class creations
    recent_classes = Class.objects.filter(
        school=school,
        created_at__gte=timezone.now() - timedelta(days=30)
    ).count()
    
    return render(request, 'core/partials/school_overview_stats.html', {
        'total_students': total_students,
        'total_staff': total_staff,
        'total_classes': total_classes,
        'full_classes': full_classes,
        'recent_classes': recent_classes,
    })
