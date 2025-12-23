# users/tests/test_models.py
from django.test import TestCase
from django.core.exceptions import ValidationError as DjangoValidationError
from users.models import User, School, Role, Profile
from core.exceptions import ValidationError

class UserModelTest(TestCase):
    def test_create_user(self):
        user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123"
        )
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(user.check_password("testpass123"))
        self.assertFalse(user.is_staff)
        self.assertTrue(user.is_active)

    def test_create_superuser(self):
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            username="admin",
            password="adminpass123"
        )
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)

    def test_email_normalization(self):
        user = User(email='TEST@EXAMPLE.COM')
        user.clean()
        self.assertEqual(user.email, 'test@example.com')

    def test_duplicate_email_validation(self):
        User.objects.create_user(
            email="duplicate@example.com",
            username="user1",
            password="pass123"
        )
        
        user2 = User(
            email="duplicate@example.com",
            username="user2"
        )
        
        with self.assertRaises(DjangoValidationError):
            user2.clean() 