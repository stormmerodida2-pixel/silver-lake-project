import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('drivers', '0008_populate_vehicle_category_fk'),
    ]

    operations = [
        migrations.RemoveField(model_name='driverapplication', name='vehicle_category'),
        migrations.RenameField(model_name='driverapplication', old_name='vehicle_category_fk', new_name='vehicle_category'),
        migrations.AlterField(
            model_name='driverapplication',
            name='vehicle_category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='driver_applications', to='fleet.vehiclecategory',
            ),
        ),
    ]
