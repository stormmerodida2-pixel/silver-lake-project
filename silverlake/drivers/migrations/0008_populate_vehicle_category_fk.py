from django.db import migrations


def populate(apps, schema_editor):
    DriverApplication = apps.get_model('drivers', 'DriverApplication')
    VehicleCategory = apps.get_model('fleet', 'VehicleCategory')

    def resolve(slug):
        if not slug:
            return None
        category, _ = VehicleCategory.objects.get_or_create(
            slug=slug, defaults={'name': slug.replace('_', ' ').title()},
        )
        return category

    for application in DriverApplication.objects.all():
        application.vehicle_category_fk = resolve(application.vehicle_category)
        application.save(update_fields=['vehicle_category_fk'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('drivers', '0007_driverapplication_vehicle_category_fk'),
        ('fleet', '0006_seed_vehicle_categories'),
    ]

    operations = [
        migrations.RunPython(populate, noop),
    ]
