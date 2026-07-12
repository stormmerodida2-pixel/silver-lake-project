import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0008_populate_category_fk'),
    ]

    operations = [
        migrations.RemoveField(model_name='vehicle', name='category'),
        migrations.RemoveField(model_name='vehiclesubmission', name='category'),
        migrations.RenameField(model_name='vehicle', old_name='category_fk', new_name='category'),
        migrations.RenameField(model_name='vehiclesubmission', old_name='category_fk', new_name='category'),
        migrations.AlterField(
            model_name='vehicle',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='vehicles', to='fleet.vehiclecategory',
            ),
        ),
        migrations.AlterField(
            model_name='vehiclesubmission',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name='vehicle_submissions', to='fleet.vehiclecategory',
            ),
        ),
    ]
