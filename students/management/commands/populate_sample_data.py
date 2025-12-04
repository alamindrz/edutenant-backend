from django.core.management.base import BaseCommand
from students.models import School, EducationLevel, ClassGroup, Parent, Student, AcademicTerm
from users.models import Profile, Role
from django.utils import timezone
from datetime import date, timedelta
import random

class Command(BaseCommand):
    help = 'Populate sample students data for testing'
    
    def handle(self, *args, **options):
        school = School.objects.first()
        
        if not school:
            self.stdout.write(self.style.ERROR('No school found. Please create a school first.'))
            return
        
        # Create Education Levels
        levels_data = [
            {'level': 'primary', 'name': 'Primary 1', 'order': 1},
            {'level': 'primary', 'name': 'Primary 2', 'order': 2},
            {'level': 'primary', 'name': 'Primary 3', 'order': 3},
            {'level': 'primary', 'name': 'Primary 4', 'order': 4},
            {'level': 'primary', 'name': 'Primary 5', 'order': 5},
            {'level': 'jss', 'name': 'JSS 1', 'order': 1},
            {'level': 'jss', 'name': 'JSS 2', 'order': 2},
            {'level': 'jss', 'name': 'JSS 3', 'order': 3},
        ]
        
        education_levels = {}
        for level_data in levels_data:
            level, created = EducationLevel.objects.get_or_create(
                school=school,
                level=level_data['level'],
                name=level_data['name'],
                defaults={'order': level_data['order']}
            )
            education_levels[level_data['name']] = level
            if created:
                self.stdout.write(f'Created education level: {level.name}')
        
        # Create Class Groups
        class_groups_data = [
            {'name': 'Primary 1A', 'level': 'Primary 1'},
            {'name': 'Primary 1B', 'level': 'Primary 1'},
            {'name': 'Primary 2A', 'level': 'Primary 2'},
            {'name': 'Primary 3A', 'level': 'Primary 3'},
            {'name': 'JSS 1A', 'level': 'JSS 1'},
            {'name': 'JSS 1B', 'level': 'JSS 1'},
            {'name': 'JSS 2A', 'level': 'JSS 2'},
        ]
        
        class_groups = {}
        for group_data in class_groups_data:
            group, created = ClassGroup.objects.get_or_create(
                school=school,
                name=group_data['name'],
                defaults={
                    'education_level': education_levels[group_data['level']],
                    'capacity': 40
                }
            )
            class_groups[group_data['name']] = group
            if created:
                self.stdout.write(f'Created class group: {group.name}')
        
        # Create Parents
        parents_data = [
            {'first_name': 'John', 'last_name': 'Smith', 'email': 'john.smith@email.com', 'phone': '08011111111'},
            {'first_name': 'Mary', 'last_name': 'Johnson', 'email': 'mary.johnson@email.com', 'phone': '08022222222'},
            {'first_name': 'David', 'last_name': 'Williams', 'email': 'david.williams@email.com', 'phone': '08033333333'},
            {'first_name': 'Sarah', 'last_name': 'Brown', 'email': 'sarah.brown@email.com', 'phone': '08044444444'},
            {'first_name': 'Michael', 'last_name': 'Davis', 'email': 'michael.davis@email.com', 'phone': '08055555555'},
        ]
        
        parents = []
        for parent_data in parents_data:
            parent, created = Parent.objects.get_or_create(
                school=school,
                email=parent_data['email'],
                defaults={
                    'first_name': parent_data['first_name'],
                    'last_name': parent_data['last_name'],
                    'phone_number': parent_data['phone'],
                    'address': '123 Sample Street, City, State'
                }
            )
            parents.append(parent)
            if created:
                self.stdout.write(f'Created parent: {parent.full_name}')
        
        # Create Students
        first_names = ['Emma', 'Noah', 'Olivia', 'Liam', 'Ava', 'William', 'Sophia', 'Mason', 'Isabella', 'James']
        last_names = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis', 'Rodriguez', 'Martinez']
        
        students_created = 0
        for i in range(50):  # Create 50 sample students
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            class_group = random.choice(list(class_groups.values()))
            parent = random.choice(parents)
            
            # Generate random date of birth (ages 5-15)
            years_ago = random.randint(5, 15)
            days_ago = random.randint(0, 365)
            date_of_birth = timezone.now().date() - timedelta(days=(years_ago * 365 + days_ago))
            
            student, created = Student.objects.get_or_create(
                school=school,
                first_name=first_name,
                last_name=last_name,
                defaults={
                    'gender': random.choice(['M', 'F']),
                    'date_of_birth': date_of_birth,
                    'parent': parent,
                    'education_level': class_group.education_level,
                    'class_group': class_group,
                    'admission_status': 'enrolled',
                    'is_active': True,
                    'admission_date': timezone.now().date() - timedelta(days=random.randint(1, 365)),
                }
            )
            
            if created:
                students_created += 1
                # Generate admission number if not auto-generated
                if not student.admission_number:
                    school_code = school.subdomain.upper()[:3] if school.subdomain else 'SCH'
                    year = student.admission_date.year
                    sequence = Student.objects.filter(school=school).count()
                    student.admission_number = f"{school_code}/{year}/{sequence:04d}"
                    student.save()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {students_created} sample students for {school.name}')
        )
        self.stdout.write(
            self.style.SUCCESS(f'Created {len(education_levels)} education levels and {len(class_groups)} class groups')
        )