# users/tests/test_onboarding.py - FIXED IMPORTS
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from users.models import School, Profile, Role
from users.services import SchoolOnboardingService

User = get_user_model()

class SchoolOnboardingTestCase(TestCase):
    """Test cases for school onboarding functionality."""
    
    def setUp(self):
        self.client = Client()
        self.onboarding_url = reverse('users:school_onboarding')
        
    def test_onboarding_page_loads(self):
        """Test that onboarding page loads successfully."""
        response = self.client.get(self.onboarding_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create Your Digital School')
    
    def test_successful_school_creation(self):
        """Test successful school creation through onboarding."""
        onboarding_data = {
            'school_name': 'Test International School',
            'subdomain': 'testinternational',
            'school_type': 'primary',
            'contact_email': 'contact@testinternational.com',
            'phone_number': '+2348000000000',
            'address': '123 Test Street, Lagos',
            'admin_email': 'principal@testinternational.com',
            'admin_first_name': 'John',
            'admin_last_name': 'Doe', 
            'admin_password': 'securepassword123',
            'admin_password_confirm': 'securepassword123',
            'terms_agreed': True,
        }
        
        response = self.client.post(self.onboarding_url, onboarding_data)
        
        # Should redirect to dashboard on success
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/dashboard/' in response.url)
        
        # Check school was created
        school = School.objects.get(subdomain='testinternational')
        self.assertEqual(school.name, 'Test International School')
        self.assertEqual(school.school_type, 'primary')
        
        # Check admin user was created
        admin_user = User.objects.get(email='principal@testinternational.com')
        self.assertTrue(admin_user.check_password('securepassword123'))
        
        # Check profile was created
        profile = Profile.objects.get(user=admin_user, school=school)
        self.assertEqual(profile.role.system_role_type, 'principal')
    
    def test_subdomain_availability_check(self):
        """Test AJAX subdomain availability endpoint."""
        # Create a school first to test taken subdomain
        School.objects.create(
            name='Existing School',
            subdomain='existing',
            school_type='primary'
        )
        
        # Check taken subdomain
        response = self.client.get('/users/onboarding/check-subdomain/?subdomain=existing')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['available'])
        self.assertTrue(len(data.get('suggestions', [])) >= 0)
        
        # Check available subdomain
        response = self.client.get('/users/onboarding/check-subdomain/?subdomain=newschool')
        data = response.json()
        self.assertTrue(data['available'])

    def test_duplicate_subdomain_validation(self):
        """Test that duplicate subdomains are rejected."""
        # Create initial school
        School.objects.create(
            name='First School',
            subdomain='myschool',
            school_type='primary'
        )
        
        onboarding_data = {
            'school_name': 'Second School',
            'subdomain': 'myschool',  # Same subdomain
            'school_type': 'primary',
            'contact_email': 'contact@secondschool.com',
            'admin_email': 'admin@secondschool.com',
            'admin_first_name': 'Jane',
            'admin_last_name': 'Smith',
            'admin_password': 'password123',
            'admin_password_confirm': 'password123',
            'terms_agreed': True,
        }
        
        response = self.client.post(self.onboarding_url, onboarding_data)
        
        # Should not redirect (form should have errors)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'This subdomain is already taken')
        
        # Only one school should exist
        self.assertEqual(School.objects.filter(subdomain='myschool').count(), 1)