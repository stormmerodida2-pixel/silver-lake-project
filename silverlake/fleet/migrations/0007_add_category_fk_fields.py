import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0006_seed_vehicle_categories'),
    ]

    operations = [
        migrations.AddField(
            model_name='vehicle',
            name='category_fk',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='vehicles_new', to='fleet.vehiclecategory',
            ),
        ),
        migrations.AddField(
            model_name='vehiclesubmission',
            name='category_fk',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='vehicle_submissions_new', to='fleet.vehiclecategory',
            ),
        ),
    ]
