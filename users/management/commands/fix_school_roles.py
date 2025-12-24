# users/management/commands/fix_school_roles.py
from django.core.management.base import BaseCommand
from users.models import School, Role
from users.services import SchoolOnboardingService

class Command(BaseCommand):
    help = 'Fix missing roles for existing schools'

    def handle(self, *args, **options):
        schools = School.objects.all()

        for school in schools:
            self.stdout.write(f"Checking roles for {school.name}...")

            # Check if principal role exists
            if not Role.objects.filter(school=school, system_role_type='principal').exists():
                self.stdout.write(f"  Creating missing principal role for {school.name}")
                self.create_principal_role(school)

            # Check if teacher role exists
            if not Role.objects.filter(school=school, system_role_type='teacher').exists():
                self.stdout.write(f"  Creating missing teacher role for {school.name}")
                self.create_teacher_role(school)

            self.stdout.write(self.style.SUCCESS(f"✓ Completed role check for {school.name}"))

    def create_principal_role(self, school):
        """Create principal role for school."""
        Role.objects.create(
            name='Principal',
            category='administration',
            school=school,
            system_role_type='principal',
            description='School principal with full administrative access',
            permissions=['*'],
            is_system_role=True,
            can_manage_roles=True,
            can_manage_staff=True,
            can_manage_students=True,
            can_manage_academics=True,
            can_manage_finances=True,
            can_view_reports=True,
            can_communicate=True,
        )

    def create_teacher_role(self, school):
        """Create teacher role for school."""
        Role.objects.create(
            name='Teacher',
            category='academic',
            school=school,
            system_role_type='teacher',
            description='Teaching staff with academic permissions',
            permissions=['manage_attendance', 'manage_scores', 'view_reports', 'communicate'],
            is_system_role=True,
            can_manage_roles=False,
            can_manage_staff=False,
            can_manage_students=True,
            can_manage_academics=True,
            can_manage_finances=False,
            can_view_reports=True,
            can_communicate=True,
        )
