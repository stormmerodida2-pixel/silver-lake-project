from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0004_remove_vehiclesubmission_photo_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='VehicleCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('slug', models.SlugField(blank=True, max_length=60, unique=True)),
                ('order', models.PositiveSmallIntegerField(default=0, help_text='Lower numbers show first')),
            ],
            options={
                'ordering': ['order', 'name'],
                'verbose_name_plural': 'vehicle categories',
            },
        ),
    ]
