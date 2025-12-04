# core/management/commands/seed_classes.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import ClassCategory, Class, School
from users.models import Staff
from django.utils import timezone

User = get_user_model()

class Command(BaseCommand):
    help = 'Seed initial class categories and classes for schools'

    def add_arguments(self, parser):
        parser.add_argument(
            '--school-id',
            type=int,
            help='Specific school ID to seed classes for (if not provided, seeds for all active schools)',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset existing classes and categories before seeding',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be created without actually creating',
        )

    def handle(self, *args, **options):
        school_id = options.get('school_id')
        reset = options.get('reset')
        dry_run = options.get('dry_run')

        # Get schools to process
        if school_id:
            schools = School.objects.filter(id=school_id, is_active=True)
            if not schools.exists():
                self.stdout.write(
                    self.style.ERROR(f"School with ID {school_id} not found or inactive")
                )
                return
        else:
            schools = School.objects.filter(is_active=True)

        if not schools.exists():
            self.stdout.write(self.style.WARNING("No active schools found"))
            return

        # Class structure templates based on school type
        CLASS_STRUCTURES = {
            'nursery': {
                'categories': [
                    {
                        'name': 'Nursery',
                        'section': 'nursery',
                        'display_order': 1,
                        'classes': [
                            {'name': 'Play Group', 'max_students': 20, 'room_number': 'NG'},
                            {'name': 'Nursery 1', 'max_students': 25, 'room_number': 'N1'},
                            {'name': 'Nursery 2', 'max_students': 25, 'room_number': 'N2'},
                            {'name': 'Nursery 3', 'max_students': 25, 'room_number': 'N3'},
                        ]
                    }
                ]
            },
            'primary': {
                'categories': [
                    {
                        'name': 'Primary',
                        'section': 'primary',
                        'display_order': 1,
                        'classes': [
                            {'name': 'Primary 1A', 'max_students': 35, 'room_number': 'P1A'},
                            {'name': 'Primary 1B', 'max_students': 35, 'room_number': 'P1B'},
                            {'name': 'Primary 2A', 'max_students': 35, 'room_number': 'P2A'},
                            {'name': 'Primary 2B', 'max_students': 35, 'room_number': 'P2B'},
                            {'name': 'Primary 3A', 'max_students': 35, 'room_number': 'P3A'},
                            {'name': 'Primary 3B', 'max_students': 35, 'room_number': 'P3B'},
                            {'name': 'Primary 4A', 'max_students': 35, 'room_number': 'P4A'},
                            {'name': 'Primary 4B', 'max_students': 35, 'room_number': 'P4B'},
                            {'name': 'Primary 5A', 'max_students': 35, 'room_number': 'P5A'},
                            {'name': 'Primary 5B', 'max_students': 35, 'room_number': 'P5B'},
                            {'name': 'Primary 6A', 'max_students': 35, 'room_number': 'P6A'},
                            {'name': 'Primary 6B', 'max_students': 35, 'room_number': 'P6B'},
                        ]
                    }
                ]
            },
            'secondary': {
                'categories': [
                    {
                        'name': 'Junior Secondary',
                        'section': 'jss',
                        'display_order': 1,
                        'classes': [
                            {'name': 'JSS 1A', 'max_students': 40, 'room_number': 'J1A'},
                            {'name': 'JSS 1B', 'max_students': 40, 'room_number': 'J1B'},
                            {'name': 'JSS 1C', 'max_students': 40, 'room_number': 'J1C'},
                            {'name': 'JSS 2A', 'max_students': 40, 'room_number': 'J2A'},
                            {'name': 'JSS 2B', 'max_students': 40, 'room_number': 'J2B'},
                            {'name': 'JSS 2C', 'max_students': 40, 'room_number': 'J2C'},
                            {'name': 'JSS 3A', 'max_students': 40, 'room_number': 'J3A'},
                            {'name': 'JSS 3B', 'max_students': 40, 'room_number': 'J3B'},
                            {'name': 'JSS 3C', 'max_students': 40, 'room_number': 'J3C'},
                        ]
                    },
                    {
                        'name': 'Senior Secondary',
                        'section': 'sss',
                        'display_order': 2,
                        'classes': [
                            {'name': 'SSS 1A', 'max_students': 40, 'room_number': 'S1A'},
                            {'name': 'SSS 1B', 'max_students': 40, 'room_number': 'S1B'},
                            {'name': 'SSS 1C', 'max_students': 40, 'room_number': 'S1C'},
                            {'name': 'SSS 2A', 'max_students': 40, 'room_number': 'S2A'},
                            {'name': 'SSS 2B', 'max_students': 40, 'room_number': 'S2B'},
                            {'name': 'SSS 2C', 'max_students': 40, 'room_number': 'S2C'},
                            {'name': 'SSS 3A', 'max_students': 40, 'room_number': 'S3A'},
                            {'name': 'SSS 3B', 'max_students': 40, 'room_number': 'S3B'},
                            {'name': 'SSS 3C', 'max_students': 40, 'room_number': 'S3C'},
                        ]
                    }
                ]
            },
            'combined': {
                'categories': [
                    {
                        'name': 'Nursery',
                        'section': 'nursery',
                        'display_order': 1,
                        'classes': [
                            {'name': 'Play Group', 'max_students': 20, 'room_number': 'NG'},
                            {'name': 'Nursery 1', 'max_students': 25, 'room_number': 'N1'},
                            {'name': 'Nursery 2', 'max_students': 25, 'room_number': 'N2'},
                        ]
                    },
                    {
                        'name': 'Primary',
                        'section': 'primary',
                        'display_order': 2,
                        'classes': [
                            {'name': 'Primary 1', 'max_students': 35, 'room_number': 'P1'},
                            {'name': 'Primary 2', 'max_students': 35, 'room_number': 'P2'},
                            {'name': 'Primary 3', 'max_students': 35, 'room_number': 'P3'},
                            {'name': 'Primary 4', 'max_students': 35, 'room_number': 'P4'},
                            {'name': 'Primary 5', 'max_students': 35, 'room_number': 'P5'},
                        ]
                    }
                ]
            },
            'full': {
                'categories': [
                    {
                        'name': 'Nursery',
                        'section': 'nursery',
                        'display_order': 1,
                        'classes': [
                            {'name': 'Play Group', 'max_students': 20, 'room_number': 'NG'},
                            {'name': 'Nursery 1', 'max_students': 25, 'room_number': 'N1'},
                            {'name': 'Nursery 2', 'max_students': 25, 'room_number': 'N2'},
                        ]
                    },
                    {
                        'name': 'Primary',
                        'section': 'primary',
                        'display_order': 2,
                        'classes': [
                            {'name': 'Primary 1', 'max_students': 35, 'room_number': 'P1'},
                            {'name': 'Primary 2', 'max_students': 35, 'room_number': 'P2'},
                            {'name': 'Primary 3', 'max_students': 35, 'room_number': 'P3'},
                            {'name': 'Primary 4', 'max_students': 35, 'room_number': 'P4'},
                            {'name': 'Primary 5', 'max_students': 35, 'room_number': 'P5'},
                            {'name': 'Primary 6', 'max_students': 35, 'room_number': 'P6'},
                        ]
                    },
                    {
                        'name': 'Junior Secondary',
                        'section': 'jss',
                        'display_order': 3,
                        'classes': [
                            {'name': 'JSS 1', 'max_students': 40, 'room_number': 'J1'},
                            {'name': 'JSS 2', 'max_students': 40, 'room_number': 'J2'},
                            {'name': 'JSS 3', 'max_students': 40, 'room_number': 'J3'},
                        ]
                    },
                    {
                        'name': 'Senior Secondary',
                        'section': 'sss',
                        'display_order': 4,
                        'classes': [
                            {'name': 'SSS 1', 'max_students': 40, 'room_number': 'S1'},
                            {'name': 'SSS 2', 'max_students': 40, 'room_number': 'S2'},
                            {'name': 'SSS 3', 'max_students': 40, 'room_number': 'S3'},
                        ]
                    }
                ]
            }
        }

        total_categories_created = 0
        total_classes_created = 0

        for school in schools:
            self.stdout.write(
                self.style.SUCCESS(f"\nProcessing school: {school.name} ({school.school_type})")
            )

            # Get appropriate class structure
            structure = CLASS_STRUCTURES.get(school.school_type, CLASS_STRUCTURES['primary'])
            
            if reset and not dry_run:
                # Delete existing classes and categories for this school
                deleted_classes = Class.objects.filter(school=school).delete()
                deleted_categories = ClassCategory.objects.filter(school=school).delete()
                self.stdout.write(
                    self.style.WARNING(f"  Reset: Deleted {deleted_classes[0]} classes and {deleted_categories[0]} categories")
                )

            # Get school principal for form master assignment
            principal = Staff.objects.filter(
                school=school, 
                position__icontains='principal'
            ).first()

            for category_config in structure['categories']:
                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Would create category: {category_config['name']}"
                    )
                    for class_config in category_config['classes']:
                        self.stdout.write(
                            f"    [DRY RUN] Would create class: {class_config['name']}"
                        )
                    continue

                # Create or get category
                category, created = ClassCategory.objects.get_or_create(
                    school=school,
                    name=category_config['name'],
                    defaults={
                        'section': category_config['section'],
                        'display_order': category_config['display_order'],
                        'description': f"{category_config['name']} section for {school.name}",
                    }
                )

                if created:
                    total_categories_created += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  Created category: {category.name}")
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(f"  Category already exists: {category.name}")
                    )

                # Create classes for this category using the new safe method
                for class_config in category_config['classes']:
                    class_obj = self.create_class_with_unique_code(
                        school=school,
                        category=category,
                        class_config=class_config,
                        principal=principal
                    )
                    
                    if class_obj:
                        total_classes_created += 1
                        self.stdout.write(
                            self.style.SUCCESS(f"    Created class: {class_obj.name} (Code: {class_obj.code})")
                        )

        # Summary
        self.stdout.write("\n" + "="*50)
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN COMPLETED - No changes were made")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"SEEDING COMPLETED: {total_categories_created} categories and {total_classes_created} classes created across {schools.count()} schools"
                )
            )

    def create_class_with_unique_code(self, school, category, class_config, principal):
        """
        Create a class with a guaranteed unique code by bypassing the model's save method
        and manually handling code generation
        """
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # Generate a base code
                base_code = self.generate_class_code(school, category, class_config)
                
                # Ensure the code is unique
                code = base_code
                counter = 1
                while Class.objects.filter(code=code).exists():
                    code = f"{base_code}_{counter}"
                    counter += 1
                
                # Check if class already exists with same name and school
                existing_class = Class.objects.filter(
                    school=school,
                    category=category,
                    name=class_config['name']
                ).first()
                
                if existing_class:
                    self.stdout.write(
                        self.style.WARNING(f"    Class already exists: {class_config['name']}")
                    )
                    return None
                
                # Create the class with the unique code
                class_obj = Class(
                    school=school,
                    category=category,
                    name=class_config['name'],
                    max_students=class_config['max_students'],
                    room_number=class_config['room_number'],
                    academic_session=f"{timezone.now().year}/{timezone.now().year + 1}",
                    form_master=principal,
                    code=code  # Set the code explicitly to bypass auto-generation
                )
                
                # Save without triggering code generation
                class_obj.save()
                return class_obj
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"    Error creating class {class_config['name']}: {str(e)}")
            )
            return None

    def generate_class_code(self, school, category, class_config):
        """
        Generate a base class code that includes school, category, and class identifiers
        """
        # Use school name initials (first 2 chars)
        school_code = ''.join([word[0] for word in school.name.split()[:2]]).upper()
        if len(school_code) < 2:
            school_code = school.name[:2].upper()
        
        # Use category section (first 2 chars)
        category_code = category.section[:2].upper()
        
        # Use class name (remove spaces and take first 3 chars)
        class_code = class_config['name'].replace(' ', '')[:3].upper()
        
        # Use room number as fallback if class code is not good
        if not class_code or class_code == class_config['name'][:3].upper():
            class_code = class_config['room_number']
        
        return f"{school_code}{category_code}{class_code}"