# management/commands/update_term_status.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from students.models import AcademicTerm

class Command(BaseCommand):
    help = 'Update academic term statuses based on current date'
    
    def handle(self, *args, **options):
        today = timezone.now().date()
        
        # Activate terms that should be active
        upcoming_terms = AcademicTerm.objects.filter(
            status='upcoming',
            start_date__lte=today
        )
        
        for term in upcoming_terms:
            term.status = 'active'
            term.is_active = True
            term.save()
            self.stdout.write(
                self.style.SUCCESS(f'Activated term: {term.name}')
            )
        
        # Close terms that have ended
        active_terms = AcademicTerm.objects.filter(status='active')
        
        for term in active_terms:
            end_date = term.actual_end_date or term.end_date
            if today > end_date:
                term.status = 'closed'
                term.is_active = False
                term.save()
                self.stdout.write(
                    self.style.SUCCESS(f'Closed term: {term.name}')
                )
        
        self.stdout.write(
            self.style.SUCCESS('Term status update completed')
        )