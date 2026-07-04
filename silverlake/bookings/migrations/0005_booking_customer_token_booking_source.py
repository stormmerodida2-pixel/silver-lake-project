import uuid

from django.db import migrations, models


def backfill_customer_tokens(apps, schema_editor):
    Booking = apps.get_model('bookings', 'Booking')
    for booking in Booking.objects.all():
        booking.customer_token = uuid.uuid4()
        booking.save(update_fields=['customer_token'])


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0004_booking_driver_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='customer_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(backfill_customer_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='booking',
            name='customer_token',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='source',
            field=models.CharField(choices=[('online', 'Online'), ('driver_onsite', 'Driver (on-site)')], default='online', max_length=20),
        ),
    ]
