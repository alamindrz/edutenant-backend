# users/management/commands/populate_sample_staff.py
from django.core.management.base import BaseCommand
from users.models import School, Staff, Role, Profile
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
import random

User = get_user_model()

class Command(BaseCommand):
    help = 'Populate sample staff data for testing'
    
    def handle(self, *args, **options):
        school = School.objects.first()
        
        if not school:
            self.stdout.write(self.style.ERROR('No school found. Please create a school first.'))
            return
        
        # Sample staff data with enhanced fields
        staff_data = [
            # Principal
            {
                'first_name': 'James', 'last_name': 'Wilson', 'email': 'principal@school.com',
                'position': 'Principal', 'department': 'Administration', 
                'gender': 'M', 'date_of_birth': date(1975, 5, 15),
                'qualification': 'M.Ed Educational Management', 'years_of_experience': 15,
                'phone_number': '08010000001', 'employment_type': 'full_time',
                'marital_status': 'married', 'nationality': 'Nigerian',
            },
            # Vice Principal
            {
                'first_name': 'Sarah', 'last_name': 'Thompson', 'email': 'vice.principal@school.com',
                'position': 'Vice Principal Academics', 'department': 'Administration',
                'gender': 'F', 'date_of_birth': date(1978, 8, 22),
                'qualification': 'M.Sc Mathematics', 'years_of_experience': 12,
                'phone_number': '08010000002', 'employment_type': 'full_time',
                'marital_status': 'married', 'nationality': 'Nigerian',
            },
            # Teachers
            {
                'first_name': 'Michael', 'last_name': 'Brown', 'email': 'michael.brown@school.com',
                'position': 'Mathematics Teacher', 'department': 'Mathematics',
                'gender': 'M', 'date_of_birth': date(1985, 3, 10),
                'qualification': 'B.Sc Mathematics', 'years_of_experience': 8,
                'phone_number': '08010000003', 'employment_type': 'full_time',
                'marital_status': 'single', 'nationality': 'Nigerian',
            },
            {
                'first_name': 'Jennifer', 'last_name': 'Davis', 'email': 'jennifer.davis@school.com',
                'position': 'English Teacher', 'department': 'Languages',
                'gender': 'F', 'date_of_birth': date(1988, 7, 18),
                'qualification': 'B.A English', 'years_of_experience': 6,
                'phone_number': '08010000004', 'employment_type': 'full_time',
                'marital_status': 'married', 'nationality': 'Nigerian',
            },
            {
                'first_name': 'Robert', 'last_name': 'Miller', 'email': 'robert.miller@school.com',
                'position': 'Science Teacher', 'department': 'Sciences',
                'gender': 'M', 'date_of_birth': date(1983, 11, 5),
                'qualification': 'B.Sc Biology', 'years_of_experience': 9,
                'phone_number': '08010000005', 'employment_type': 'full_time',
                'marital_status': 'married', 'nationality': 'Nigerian',
            },
            # Support Staff
            {
                'first_name': 'Thomas', 'last_name': 'Clark', 'email': 'thomas.clark@school.com',
                'position': 'IT Support Officer', 'department': 'ICT',
                'gender': 'M', 'date_of_birth': date(1990, 2, 28),
                'qualification': 'B.Tech Computer Science', 'years_of_experience': 4,
                'phone_number': '08010000006', 'employment_type': 'full_time',
                'marital_status': 'single', 'nationality': 'Nigerian', 'is_teaching_staff': False,
            },
            {
                'first_name': 'Nancy', 'last_name': 'Rodriguez', 'email': 'nancy.rodriguez@school.com',
                'position': 'Librarian', 'department': 'Library',
                'gender': 'F', 'date_of_birth': date(1987, 9, 14),
                'qualification': 'B.L.S Library Science', 'years_of_experience': 5,
                'phone_number': '08010000007', 'employment_type': 'full_time',
                'marital_status': 'married', 'nationality': 'Nigerian', 'is_teaching_staff': False,
            },
        ]
        
        staff_created = 0
        for i, staff_info in enumerate(staff_data):
            # Calculate employment date (1-10 years ago)
            employment_date = timezone.now().date() - timedelta(days=random.randint(365, 3650))
            
            staff, created = Staff.objects.get_or_create(
                school=school,
                email=staff_info['email'],
                defaults={
                    'first_name': staff_info['first_name'],
                    'last_name': staff_info['last_name'],
                    'gender': staff_info['gender'],
                    'date_of_birth': staff_info['date_of_birth'],
                    'position': staff_info['position'],
                    'department': staff_info['department'],
                    'phone_number': staff_info['phone_number'],
                    'employment_type': staff_info['employment_type'],
                    'date_joined': employment_date,
                    'qualification': staff_info['qualification'],
                    'years_of_experience': staff_info['years_of_experience'],
                    'marital_status': staff_info['marital_status'],
                    'nationality': staff_info['nationality'],
                    'is_teaching_staff': staff_info.get('is_teaching_staff', True),
                    'address': '123 School Staff Quarters, City, State',
                    'emergency_contact_name': f"Emergency Contact {staff_info['first_name']}",
                    'emergency_contact_phone': f'0809999{1000 + i}',
                    'emergency_contact_relationship': 'Spouse',
                }
            )
            
            if created:
                staff_created += 1
                self.stdout.write(f'Created staff: {staff.full_name} - {staff.position}')
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {staff_created} staff members for {school.name}')
        )