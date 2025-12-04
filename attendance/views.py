# attendance/views.py - FIXED IMPORTS
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q, Count, Avg, Sum
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.core.paginator import Paginator

from core.decorators import require_role, require_school_context
from .models import (
    StudentAttendance, TeacherAttendance, AttendanceConfig,
    AttendanceSummary, TeacherPerformance
)
from students.models import Student, ClassGroup, AcademicTerm
# FIX: Import Staff from users app - this is the correct import based on your models
from users.models import Staff, Profile

logger = logging.getLogger(__name__)






@login_required
@require_school_context
def attendance_dashboard_view(request):
    """
    Attendance dashboard for school administrators.
    Provides comprehensive attendance overview with:
    - Student attendance stats and rates
    - Teacher attendance and sign-in metrics  
    - Class group attendance ranking
    - Recent attendance records
    - Current term context
    """
    school = request.school

    try:
        # Initialize all variables with safe defaults first
        student_stats = {
            'total_students': 0,
            'present_today': 0,
            'absent_today': 0,
            'late_today': 0,
            'present_rate': 0,
        }
        
        teacher_stats = {
            'total_teachers': 0,
            'present_today': 0,
            'signed_in_today': 0,
            'late_today': 0,
            'signin_rate': 0,
        }
        
        class_group_attendance = []
        recent_student_attendance = []
        recent_teacher_attendance = []
        current_term = None
        today = timezone.now().date()
        is_school_day = True

        # ---------------------------
        # Current term
        # ---------------------------
        try:
            current_term = AcademicTerm.objects.filter(
                school=school, is_active=True
            ).first()

            if not current_term:
                messages.warning(request, "No active academic term found.")
        except Exception as e:
            logger.warning(f"Error getting current term: {e}")

        # ---------------------------
        # Student statistics
        # ---------------------------
        try:
            total_students = Student.objects.filter(
                school=school, is_active=True
            ).count()

            present_today = StudentAttendance.objects.filter(
                student__school=school,
                date=today,
                status='present'
            ).count()

            absent_today = StudentAttendance.objects.filter(
                student__school=school,
                date=today,
                status='absent'
            ).count()

            late_today = StudentAttendance.objects.filter(
                student__school=school,
                date=today,
                status='late'
            ).count()

            # Safe percentage calculation
            student_present_rate = (
                (present_today / total_students) * 100 if total_students > 0 else 0
            )

            student_stats = {
                'total_students': total_students,
                'present_today': present_today,
                'absent_today': absent_today,
                'late_today': late_today,
                'present_rate': round(student_present_rate, 1),
            }
        except Exception as e:
            logger.error(f"Error calculating student stats: {e}")
            messages.warning(request, "Could not load student statistics")

        # ---------------------------
        # Teacher statistics
        # ---------------------------
        try:
            total_teachers = Staff.objects.filter(
                school=school, is_active=True
            ).count()

            teacher_present_today = TeacherAttendance.objects.filter(
                staff__school=school,
                date=today,
                status='present'
            ).count()

            teacher_signed_in_today = TeacherAttendance.objects.filter(
                staff__school=school,
                date=today,
                sign_in_time__isnull=False
            ).count()

            teacher_late_today = TeacherAttendance.objects.filter(
                staff__school=school,
                date=today,
                is_late=True
            ).count()

            teacher_signin_rate = (
                (teacher_signed_in_today / total_teachers) * 100
                if total_teachers > 0 else 0
            )

            teacher_stats = {
                'total_teachers': total_teachers,
                'present_today': teacher_present_today,
                'signed_in_today': teacher_signed_in_today,
                'late_today': teacher_late_today,
                'signin_rate': round(teacher_signin_rate, 1),
            }
        except Exception as e:
            logger.error(f"Error calculating teacher stats: {e}")
            messages.warning(request, "Could not load teacher statistics")

        # ---------------------------
        # Class group attendance ranking
        # ---------------------------
        try:
            class_groups = ClassGroup.objects.filter(school=school)
            
            for cg in class_groups:
                # Use actual count from database for safety
                cg_total = Student.objects.filter(
                    class_group=cg, is_active=True
                ).count()

                cg_present = StudentAttendance.objects.filter(
                    student__class_group=cg,
                    date=today,
                    status='present'
                ).count()

                cg_rate = (cg_present / cg_total * 100) if cg_total > 0 else 0

                class_group_attendance.append({
                    'class_group': cg,
                    'present_count': cg_present,
                    'total_students': cg_total,
                    'attendance_rate': round(cg_rate, 1),
                })

            # Sort by attendance % (highest first)
            class_group_attendance.sort(
                key=lambda x: x['attendance_rate'], reverse=True
            )
        except Exception as e:
            logger.error(f"Error calculating class group attendance: {e}")
            messages.warning(request, "Could not load class group rankings")

        # ---------------------------
        # Recent attendance records
        # ---------------------------
        try:
            recent_student_attendance = StudentAttendance.objects.filter(
                student__school=school,
                date=today
            ).select_related(
                'student', 'student__class_group'
            ).order_by('-recorded_at')[:10]
        except Exception as e:
            logger.error(f"Error loading recent student attendance: {e}")

        try:
            recent_teacher_attendance = TeacherAttendance.objects.filter(
                staff__school=school,
                date=today,
                sign_in_time__isnull=False
            ).select_related(
                'staff'
            ).order_by('-sign_in_time')[:10]
        except Exception as e:
            logger.error(f"Error loading recent teacher attendance: {e}")

        # Check if today is a valid school day
        if current_term:
            try:
                is_school_day = current_term.is_school_day(today)
                if not is_school_day:
                    messages.info(request, f"Today is not a school day for {current_term.name}")
            except Exception as e:
                logger.warning(f"Error checking school day status: {e}")

        # ---------------------------
        # Build context
        # ---------------------------
        context = {
            'student_stats': student_stats,
            'teacher_stats': teacher_stats,
            'class_group_attendance': class_group_attendance[:6],  # Top 6 classes
            'recent_student_attendance': recent_student_attendance,
            'recent_teacher_attendance': recent_teacher_attendance,
            'current_term': current_term,
            'today': today,
            'is_school_day': is_school_day,
            'school': school,
        }

        logger.info(f"Attendance dashboard accessed for school {school.name}")
        return render(request, 'attendance/dashboard.html', context)

    except Exception as e:
        logger.error(f"Dashboard fatal error: {e}")
        messages.error(request, "Error loading attendance dashboard")
        
        # Return a safe context even on fatal errors
        safe_context = {
            'student_stats': {'total_students': 0, 'present_today': 0, 'absent_today': 0, 'late_today': 0, 'present_rate': 0},
            'teacher_stats': {'total_teachers': 0, 'present_today': 0, 'signed_in_today': 0, 'late_today': 0, 'signin_rate': 0},
            'class_group_attendance': [],
            'recent_student_attendance': [],
            'recent_teacher_attendance': [],
            'current_term': None,
            'today': timezone.now().date(),
            'is_school_day': True,
            'school': school,
        }
        return render(request, 'attendance/dashboard.html', safe_context)




@login_required
@require_school_context
@require_role('manage_attendance')
def student_attendance_list_view(request):
    """List and manage student attendance."""
    school = request.school
    
    try:
        # Get current academic term
        from students.models import AcademicTerm
        current_term = AcademicTerm.objects.filter(school=school, is_active=True).first()
        
        # Filters
        date_filter = request.GET.get('date', timezone.now().date().isoformat())
        class_filter = request.GET.get('class_group', '')
        status_filter = request.GET.get('status', '')
        
        try:
            selected_date = datetime.fromisoformat(date_filter).date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
        
        # Get attendance records for selected date
        attendance_records = StudentAttendance.objects.filter(
            student__school=school,
            date=selected_date
        ).select_related('student', 'student__class_group', 'recorded_by')
        
        if class_filter:
            attendance_records = attendance_records.filter(student__class_group_id=class_filter)
        
        if status_filter:
            attendance_records = attendance_records.filter(status=status_filter)
        
        # Get class groups for filter - USING YOUR EXISTING ClassGroup MODEL
        from students.models import ClassGroup
        class_groups = ClassGroup.objects.filter(school=school)
        
        # Get students without attendance records for the day
        students_without_attendance = Student.objects.filter(
            school=school,
            is_active=True
        ).exclude(
            id__in=attendance_records.values_list('student_id', flat=True)
        )
        
        if class_filter:
            students_without_attendance = students_without_attendance.filter(
                class_group_id=class_filter
            )
        
        if request.method == 'POST':
            # Handle bulk attendance update
            if 'bulk_attendance' in request.POST:
                return _handle_bulk_attendance(request, school, selected_date)
        
        context = {
            'attendance_records': attendance_records,
            'students_without_attendance': students_without_attendance,
            'class_groups': class_groups,
            'selected_date': selected_date,
            'class_filter': class_filter,
            'status_filter': status_filter,
            'current_term': current_term,
        }
        
        return render(request, 'attendance/student_attendance_list.html', context)
        
    except Exception as e:
        logger.error(f"Student attendance list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading student attendance. Please try again.")
        return redirect('attendance:dashboard')




@login_required
@require_school_context
@require_role('manage_attendance')
def class_group_attendance_view(request):
    """Class group-level attendance overview."""
    school = request.school
    
    try:
        # Get current academic term
        from students.models import AcademicTerm
        current_term = AcademicTerm.objects.filter(school=school, is_active=True).first()
        
        # Filters
        date_filter = request.GET.get('date', timezone.now().date().isoformat())
        class_filter = request.GET.get('class_group', '')
        
        try:
            selected_date = datetime.fromisoformat(date_filter).date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
        
        # Get all class groups for the school
        from students.models import ClassGroup
        class_groups = ClassGroup.objects.filter(school=school)
        
        if class_filter:
            class_groups = class_groups.filter(id=class_filter)
        
        # Calculate attendance for each class group
        class_attendance = []
        for class_group in class_groups:
            # Get total students in class group
            total_students = class_group.student_count
            
            # Get attendance records for this date
            present_count = StudentAttendance.objects.filter(
                student__class_group=class_group,
                date=selected_date,
                status='present'
            ).count()
            
            attendance_rate = (present_count / total_students * 100) if total_students > 0 else 0
            
            class_attendance.append({
                'class_group': class_group,
                'total_students': total_students,
                'present_count': present_count,
                'absent_count': total_students - present_count,
                'attendance_rate': round(attendance_rate, 1),
                'class_teacher': class_group.class_teacher,
            })
        
        context = {
            'class_attendance': class_attendance,
            'class_groups': class_groups,
            'selected_date': selected_date,
            'class_filter': class_filter,
            'current_term': current_term,
        }
        
        return render(request, 'attendance/class_group_attendance.html', context)
        
    except Exception as e:
        logger.error(f"Class group attendance view error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading class group attendance. Please try again.")
        return redirect('attendance:dashboard')




@login_required
@require_school_context
@require_role('manage_attendance')
def class_attendance_view(request):
    """Class-level attendance overview."""
    school = request.school
    
    try:
        # Get current academic term
        from students.models import AcademicTerm
        current_term = AcademicTerm.objects.filter(school=school, is_active=True).first()
        
        # Filters
        date_filter = request.GET.get('date', timezone.now().date().isoformat())
        class_filter = request.GET.get('class_group', '')
        
        try:
            selected_date = datetime.fromisoformat(date_filter).date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
        
        # Get all active classes
        from core.models import Class
        classes = Class.objects.filter(school=school, is_active=True)
        
        if class_filter:
            classes = classes.filter(id=class_filter)
        
        # Calculate attendance for each class
        class_attendance = []
        for class_obj in classes:
            # Get total students in class
            total_students = class_obj.current_strength
            
            # Get attendance records for this date
            present_count = StudentAttendance.objects.filter(
                student__current_class=class_obj,
                date=selected_date,
                status='present'
            ).count()
            
            attendance_rate = (present_count / total_students * 100) if total_students > 0 else 0
            
            class_attendance.append({
                'class': class_obj,
                'total_students': total_students,
                'present_count': present_count,
                'absent_count': total_students - present_count,
                'attendance_rate': round(attendance_rate, 1),
                'form_master': class_obj.form_master,
            })
        
        context = {
            'class_attendance': class_attendance,
            'classes': classes,
            'selected_date': selected_date,
            'class_filter': class_filter,
            'current_term': current_term,
        }
        
        return render(request, 'attendance/class_attendance.html', context)
        
    except Exception as e:
        logger.error(f"Class attendance view error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading class attendance. Please try again.")
        return redirect('attendance:dashboard')


def _handle_bulk_attendance(request, school, selected_date):
    """Handle bulk attendance updates."""
    try:
        attendance_data = {}
        for key, value in request.POST.items():
            if key.startswith('attendance_'):
                student_id = key.split('_')[1]
                attendance_data[student_id] = value
        
        recorded_count = 0
        for student_id, status in attendance_data.items():
            try:
                student = Student.objects.get(id=student_id, school=school)
                
                # Get or create attendance record
                attendance, created = StudentAttendance.objects.get_or_create(
                    student=student,
                    date=selected_date,
                    defaults={
                        'academic_term': student.academic_term,
                        'status': status,
                        'recorded_by': request.user.profile_set.get(school=school),
                    }
                )
                
                if not created:
                    attendance.status = status
                    attendance.recorded_by = request.user.profile_set.get(school=school)
                    attendance.save()
                
                recorded_count += 1
                
            except Student.DoesNotExist:
                continue
        
        messages.success(request, f"Attendance recorded for {recorded_count} students.")
        
    except Exception as e:
        logger.error(f"Bulk attendance error: {str(e)}")
        messages.error(request, "Error recording attendance. Please try again.")
    
    return redirect('attendance:student_attendance_list')


@login_required
@require_school_context
@require_role('manage_staff')
def teacher_attendance_list_view(request):
    """List and manage teacher attendance."""
    school = request.school
    
    try:
        # Get current academic term
        from students.models import AcademicTerm
        current_term = AcademicTerm.objects.filter(school=school, is_active=True).first()
        
        # Filters
        date_filter = request.GET.get('date', timezone.now().date().isoformat())
        status_filter = request.GET.get('status', '')
        
        try:
            selected_date = datetime.fromisoformat(date_filter).date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
        
        # Get attendance records for selected date
        attendance_records = TeacherAttendance.objects.filter(
            staff__school=school,
            date=selected_date
        ).select_related('staff', 'recorded_by')
        
        if status_filter:
            attendance_records = attendance_records.filter(status=status_filter)
        
        # Get teachers without attendance records for the day
        teachers_without_attendance = Staff.objects.filter(
            school=school,
            is_active=True
        ).exclude(
            id__in=attendance_records.values_list('staff_id', flat=True)
        )
        
        context = {
            'attendance_records': attendance_records,
            'teachers_without_attendance': teachers_without_attendance,
            'selected_date': selected_date,
            'status_filter': status_filter,
            'current_term': current_term,
        }
        
        return render(request, 'attendance/teacher_attendance_list.html', context)
        
    except Exception as e:
        logger.error(f"Teacher attendance list error for school {school.id}: {str(e)}")
        messages.error(request, "Error loading teacher attendance. Please try again.")
        return redirect('attendance:dashboard')



@login_required
@require_school_context
@require_role('manage_staff')
def teacher_signin_view(request, staff_id):
    """Record teacher sign-in."""
    school = request.school
    
    try:
        staff = get_object_or_404(Staff, id=staff_id, school=school)
        
        # Get current academic term
        current_term = AcademicTerm.objects.filter(school=school, is_active=True).first()
        
        if not current_term:
            messages.error(request, "No active academic term found.")
            return redirect('attendance:teacher_attendance_list')
        
        today = timezone.now().date()
        
        # Get user profile for recording
        try:
            # FIX: Get the user's profile for this school
            recorded_by = Profile.objects.get(user=request.user, school=school)
        except Profile.DoesNotExist:
            # Fallback: get any profile for the user
            recorded_by = Profile.objects.filter(user=request.user).first()
            if not recorded_by:
                messages.error(request, "User profile not found.")
                return redirect('attendance:teacher_attendance_list')
        
        # Get or create attendance record
        attendance, created = TeacherAttendance.objects.get_or_create(
            staff=staff,
            date=today,
            defaults={
                'academic_term': current_term,
                'status': 'present',
                'sign_in_time': timezone.now(),
                'recorded_by': recorded_by,
            }
        )
        
        if not created:
            # Update existing record
            if attendance.sign_in_time:
                messages.warning(request, f"{staff.full_name} has already signed in today.")
            else:
                attendance.sign_in_time = timezone.now()
                attendance.status = 'present'
                attendance.recorded_by = recorded_by
                attendance.save()
                messages.success(request, f"{staff.full_name} signed in successfully.")
        
        else:
            messages.success(request, f"{staff.full_name} signed in successfully.")
        
        logger.info(f"Teacher sign-in recorded: {staff.full_name} by {request.user.email}")
        
    except Exception as e:
        logger.error(f"Teacher sign-in error: {str(e)}")
        messages.error(request, "Error recording sign-in. Please try again.")
    
    return redirect('attendance:teacher_attendance_list')



@login_required
@require_school_context
@require_role('manage_staff')
def teacher_signout_view(request, staff_id):
    """Record teacher sign-out."""
    school = request.school
    
    try:
        staff = get_object_or_404(Staff, id=staff_id, school=school)
        today = timezone.now().date()
        
        # Get today's attendance record
        attendance = get_object_or_404(
            TeacherAttendance,
            staff=staff,
            date=today,
            sign_in_time__isnull=False
        )
        
        if attendance.sign_out_time:
            messages.warning(request, f"{staff.full_name} has already signed out today.")
        else:
            attendance.sign_out_time = timezone.now()
            attendance.save()
            messages.success(request, f"{staff.full_name} signed out successfully.")
            logger.info(f"Teacher sign-out recorded: {staff.full_name} by {request.user.email}")
        
    except TeacherAttendance.DoesNotExist:
        messages.error(request, f"No sign-in record found for {staff.full_name} today.")
    except Exception as e:
        logger.error(f"Teacher sign-out error: {str(e)}")
        messages.error(request, "Error recording sign-out. Please try again.")
    
    return redirect('attendance:teacher_attendance_list')


@login_required
@require_school_context
@require_role('manage_attendance')
def attendance_reports_view(request):
    """Generate attendance reports."""
    school = request.school
    
    try:
        # Get current academic term
        from students.models import AcademicTerm
        current_term = AcademicTerm.objects.filter(school=school, is_active=True).first()
        
        if not current_term:
            messages.warning(request, "No active academic term found.")
            return render(request, 'attendance/reports.html', {})
        
        # Report parameters
        report_type = request.GET.get('report_type', 'student')
        period = request.GET.get('period', 'monthly')
        date_from = request.GET.get('date_from', (timezone.now() - timedelta(days=30)).date().isoformat())
        date_to = request.GET.get('date_to', timezone.now().date().isoformat())
        
        try:
            date_from = datetime.fromisoformat(date_from).date()
            date_to = datetime.fromisoformat(date_to).date()
        except (ValueError, TypeError):
            date_from = (timezone.now() - timedelta(days=30)).date()
            date_to = timezone.now().date()
        
        if report_type == 'student':
            # Student attendance report
            attendance_data = StudentAttendance.objects.filter(
                student__school=school,
                date__range=[date_from, date_to]
            ).values(
                'student__first_name',
                'student__last_name',
                'student__class_group__name',
                'status'
            ).annotate(
                count=Count('id')
            ).order_by('student__class_group__name', 'student__first_name')
            
            # Calculate summary
            summary = {
                'total_records': StudentAttendance.objects.filter(
                    student__school=school,
                    date__range=[date_from, date_to]
                ).count(),
                'present_count': StudentAttendance.objects.filter(
                    student__school=school,
                    date__range=[date_from, date_to],
                    status='present'
                ).count(),
                'absent_count': StudentAttendance.objects.filter(
                    student__school=school,
                    date__range=[date_from, date_to],
                    status='absent'
                ).count(),
            }
            
        else:
            # Teacher attendance report
            attendance_data = TeacherAttendance.objects.filter(
                staff__school=school,
                date__range=[date_from, date_to]
            ).values(
                'staff__first_name',
                'staff__last_name',
                'status'
            ).annotate(
                count=Count('id')
            ).order_by('staff__first_name')
            
            # Calculate summary
            summary = {
                'total_records': TeacherAttendance.objects.filter(
                    staff__school=school,
                    date__range=[date_from, date_to]
                ).count(),
                'present_count': TeacherAttendance.objects.filter(
                    staff__school=school,
                    date__range=[date_from, date_to],
                    status='present'
                ).count(),
                'signed_in_count': TeacherAttendance.objects.filter(
                    staff__school=school,
                    date__range=[date_from, date_to],
                    sign_in_time__isnull=False
                ).count(),
            }
        
        context = {
            'report_type': report_type,
            'period': period,
            'date_from': date_from,
            'date_to': date_to,
            'attendance_data': attendance_data,
            'summary': summary,
            'current_term': current_term,
        }
        
        return render(request, 'attendance/reports.html', context)
        
    except Exception as e:
        logger.error(f"Attendance reports error for school {school.id}: {str(e)}")
        messages.error(request, "Error generating reports. Please try again.")
        return redirect('attendance:dashboard')


# HTMX Views
@login_required
@require_school_context
def student_attendance_table_partial(request):
    """HTMX endpoint for student attendance table."""
    school = request.school
    
    try:
        date_filter = request.GET.get('date', timezone.now().date().isoformat())
        class_filter = request.GET.get('class_group', '')
        
        try:
            selected_date = datetime.fromisoformat(date_filter).date()
        except (ValueError, TypeError):
            selected_date = timezone.now().date()
        
        attendance_records = StudentAttendance.objects.filter(
            student__school=school,
            date=selected_date
        ).select_related('student', 'student__class_group')
        
        if class_filter:
            attendance_records = attendance_records.filter(student__class_group_id=class_filter)
        
        context = {
            'attendance_records': attendance_records,
            'selected_date': selected_date,
        }
        
        return render(request, 'attendance/partials/student_attendance_table.html', context)
        
    except Exception as e:
        logger.error(f"Student attendance table partial error: {str(e)}")
        return render(request, 'attendance/partials/error.html', {'message': 'Error loading attendance data'})