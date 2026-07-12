from django.db import migrations


def resolver(VehicleCategory):
    def resolve(slug):
        if not slug:
            return None
        category, _ = VehicleCategory.objects.get_or_create(
            slug=slug, defaults={'name': slug.replace('_', ' ').title()},
        )
        return category
    return resolve


def populate(apps, schema_editor):
    Vehicle = apps.get_model('fleet', 'Vehicle')
    VehicleSubmission = apps.get_model('fleet', 'VehicleSubmission')
    VehicleCategory = apps.get_model('fleet', 'VehicleCategory')
    resolve = resolver(VehicleCategory)

    for vehicle in Vehicle.objects.all():
        vehicle.category_fk = resolve(vehicle.category)
        vehicle.save(update_fields=['category_fk'])

    for submission in VehicleSubmission.objects.all():
        submission.category_fk = resolve(submission.category)
        submission.save(update_fields=['category_fk'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0007_add_category_fk_fields'),
    ]

    operations = [
        migrations.RunPython(populate, noop),
    ]
