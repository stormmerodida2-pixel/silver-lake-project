import re

from django.core.exceptions import ValidationError

# A real Kenyan mobile number, normalized to the exact shape every phone input in this app
# submits (see frontend/src/components/PhoneInput.vue): '254' followed by the network digit
# (7 for Safaricom/Airtel/Telkom mobile, 1 for the newer 254 1XX mobile ranges) and exactly 8
# more digits - e.g. '254712345678'. Deliberately strict (no '+', no leading '0', no spaces) -
# PhoneInput.vue is the only place a phone number is ever typed in this app, and it always emits
# this exact shape, so the backend enforcing the same shape catches a request that bypassed it
# (a stray direct API call) rather than silently accepting or half-normalizing something else.
KENYAN_PHONE_PATTERN = re.compile(r'^254[17]\d{8}$')


def validate_kenyan_phone_number(value):
    if not KENYAN_PHONE_PATTERN.match(value or ''):
        raise ValidationError(
            'Enter a valid Kenyan phone number (254 followed by 7 or 1, then 8 digits - e.g. 254712345678).'
        )
