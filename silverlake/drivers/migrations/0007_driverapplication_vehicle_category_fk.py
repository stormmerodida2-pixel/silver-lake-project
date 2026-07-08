import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('drivers', '0006_driver_suspension_reason'),
        ('fleet', '0005_vehiclecategory'),
    ]

    operations = [
        migrations.AddField(
            model_name='driverapplication',
            name='vehicle_category_fk',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='driver_applications_new', to='fleet.vehiclecategory',
            ),
        ),
    ]
