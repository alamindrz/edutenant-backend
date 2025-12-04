# users/tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError
from users.models import User, School, Role, Profile

class UserModelTest(TestCase):
    def test_create_user_with_email(self):
        """Test creating user with email works."""
        user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self.assertEqual(user.email, 'test@example.com')
        self.assertTrue(user.check_password('testpass123'))
        self.assertFalse(user.is_staff)

    def test_create_superuser(self):
        """Test creating superuser works."""
        admin_user = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123'
        )
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)

class SchoolModelTest(TestCase):
    def test_create_school(self):
        """Test school creation."""
        school = School.objects.create(
            name='Test School',
            subdomain='testschool',
            school_type='primary'
        )
        self.assertEqual(str(school), 'Test School (testschool)')
        self.assertEqual(school.subdomain_status, 'pending')

    def test_subdomain_active_property(self):
        """Test is_subdomain_active property."""
        from django.utils import timezone
        from datetime import timedelta
        
        school = School.objects.create(
            name='Test School',
            subdomain='testschool',
            subdomain_status='active',
            subdomain_expires_at=timezone.now() + timedelta(days=30)
        )
        self.assertTrue(school.is_subdomain_active)

class RoleModelTest(TestCase):
    def test_create_role(self):
        """Test role creation."""
        school = School.objects.create(name='Test School', subdomain='test')
        role = Role.objects.create(
            name='Principal',
            category='administration',
            school=school,
            permissions=['*'],
            is_system_role=True
        )
        self.assertEqual(str(role), 'Principal - Test School')