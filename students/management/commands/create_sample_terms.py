from django.core.management.base import BaseCommand
from students.models import AcademicTerm, School
from django.utils import timezone
from datetime import timedelta

class Command(BaseCommand):
    help = 'Create sample academic terms for testing'
    
    def handle(self, *args, **options):
        school = School.objects.first()
        
        if not school:
            self.stdout.write(self.style.ERROR('No school found. Please create a school first.'))
            return
        
        # Create current active term
        current_term = AcademicTerm.objects.create(
            school=school,
            name="First Term 2024",
            term="first",
            academic_year="2024/2025",
            start_date=timezone.now().date() - timedelta(days=30),
            end_date=timezone.now().date() + timedelta(days=60),
            status="active",
            is_active=True,
            planned_weeks=13,
        )
        
        # Create upcoming term
        upcoming_term = AcademicTerm.objects.create(
            school=school,
            name="Second Term 2024",
            term="second", 
            academic_year="2024/2025",
            start_date=timezone.now().date() + timedelta(days=70),
            end_date=timezone.now().date() + timedelta(days=130),
            status="upcoming",
            is_active=False,
            planned_weeks=12,
        )
        
        # Create past term
        past_term = AcademicTerm.objects.create(
            school=school,
            name="Third Term 2023",
            term="third",
            academic_year="2023/2024",
            start_date=timezone.now().date() - timedelta(days=180),
            end_date=timezone.now().date() - timedelta(days=120),
            status="closed",
            is_active=False,
            planned_weeks=12,
        )
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created 3 sample terms for {school.name}')
        ) 