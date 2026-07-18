import random
import string

from django.db import migrations


def generate_code(CustomerProfile):
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(alphabet, k=8))
        if not CustomerProfile.objects.filter(referral_code=code).exists():
            return code


def backfill(apps, schema_editor):
    CustomerProfile = apps.get_model('accounts', 'CustomerProfile')
    for profile in CustomerProfile.objects.filter(referral_code__isnull=True):
        profile.referral_code = generate_code(CustomerProfile)
        profile.save(update_fields=['referral_code'])


def noop_reverse(apps, schema_editor):
    # Nothing to undo - referral_code just goes back to being unused once the field itself is
    # removed by reversing the previous migration.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_customerprofile_referral_code_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
