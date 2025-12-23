# users/management/commands/fix_school_context.py
from django.core.management.base import BaseCommand
from users.models import User, Profile

class Command(BaseCommand):
    help = 'Fix school context for users with missing current_school'

    def handle(self, *args, **options):
        users_fixed = 0
        for user in User.objects.filter(current_school__isnull=True):
            profile = Profile.objects.filter(user=user).first()
            if profile:
                user.current_school = profile.school
                user.save()
                users_fixed += 1
                self.stdout.write(f"Fixed school context for {user.email}")

        self.stdout.write(
            self.style.SUCCESS(f'Successfully fixed school context for {users_fixed} users')
        )
