from django.db import migrations

SEED = [
    ('executive_suv', 'Executive SUV', 0),
    ('premium_mpv', 'Premium MPV', 1),
    ('compact_sedan', 'Compact Sedan', 2),
    ('passenger_van', 'Passenger Van', 3),
]


def seed_categories(apps, schema_editor):
    VehicleCategory = apps.get_model('fleet', 'VehicleCategory')
    for slug, name, order in SEED:
        VehicleCategory.objects.get_or_create(slug=slug, defaults={'name': name, 'order': order})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0005_vehiclecategory'),
    ]

    operations = [
        migrations.RunPython(seed_categories, noop),
    ]
