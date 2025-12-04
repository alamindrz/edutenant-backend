# users/tests/test_services.py
from django.test import TestCase
from users.services import SchoolOnboardingService
from users.models import School, User, Profile, Role

class SchoolOnboardingServiceTest(TestCase):
    def test_is_subdomain_available(self):
        """Test subdomain availability checking."""
        # Initially should be available
        self.assertTrue(SchoolOnboardingService.is_subdomain_available('newschool'))
        
        # Create school and check again
        School.objects.create(name='Test', subdomain='newschool')
        self.assertFalse(SchoolOnboardingService.is_subdomain_available('newschool'))
    
    def test_get_subdomain_suggestions(self):
        """Test subdomain suggestion generation."""
        School.objects.create(name='Test', subdomain='myschool')
        
        suggestions = SchoolOnboardingService.get_subdomain_suggestions('myschool')
        self.assertTrue(len(suggestions) > 0)
        # All suggestions should be available
        for suggestion in suggestions:
            self.assertTrue(SchoolOnboardingService.is_subdomain_available(suggestion))