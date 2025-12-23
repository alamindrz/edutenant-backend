# core/tests/test_middleware.py
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from users.models import School, Role, Profile
from core.middleware import SubdomainMiddleware

User = get_user_model()

class SubdomainMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = SubdomainMiddleware(lambda r: None)
        
        self.school = School.objects.create(
            name="Test School",
            subdomain="test",
            subdomain_status="active",
            is_active=True
        )
        
        self.user = User.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="testpass123"
        )

    def test_subdomain_extraction(self):
        request = self.factory.get('/')
        request.META['HTTP_HOST'] = 'test.edusuite.localhost:8000'
        
        subdomain = self.middleware.extract_subdomain(request.META['HTTP_HOST'])
        self.assertEqual(subdomain, 'test')

    def test_valid_subdomain_school_found(self):
        request = self.factory.get('/')
        request.META['HTTP_HOST'] = 'test.edusuite.localhost:8000'
        
        self.middleware(request)
        self.assertEqual(request.school, self.school)

    def test_invalid_subdomain_no_school(self):
        request = self.factory.get('/')
        request.META['HTTP_HOST'] = 'invalid.edusuite.localhost:8000'
        
        self.middleware(request)
        self.assertIsNone(request.school) 