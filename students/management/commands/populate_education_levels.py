# students/management/commands/populate_education_levels.py
from django.core.management.base import BaseCommand
from students.models import EducationLevel, School

class Command(BaseCommand):
    help = 'Populate education levels for existing schools'

    def handle(self, *args, **options):
        schools = School.objects.all()
        
        level_templates = {
            'nursery': [
                ('Playgroup', 0),
                ('Nursery 1', 1),
                ('Nursery 2', 2),
                ('Kindergarten', 3),
            ],
            'primary': [
                ('Primary 1', 0),
                ('Primary 2', 1),
                ('Primary 3', 2),
                ('Primary 4', 3),
                ('Primary 5', 4),
                ('Primary 6', 5),
            ],
            'jss': [
                ('JSS 1', 0),
                ('JSS 2', 1),
                ('JSS 3', 2),
            ],
            'sss': [
                ('SSS 1', 0),
                ('SSS 2', 1),
                ('SSS 3', 2),
            ]
        }
        
        created_count = 0
        
        for school in schools:
            for level_type, levels in level_templates.items():
                for level_name, order in levels:
                    # Check if level already exists
                    if not EducationLevel.objects.filter(
                        school=school, 
                        level=level_type, 
                        name=level_name
                    ).exists():
                        EducationLevel.objects.create(
                            school=school,
                            level=level_type,
                            name=level_name,
                            order=order
                        )
                        created_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created {created_count} education levels')
        )