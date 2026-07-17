"""Africa's Talking SMS client - mirrors payments/mpesa.py's own shape (a thin wrapper that
raises on failure rather than swallowing it) so this module is safe to reuse anywhere; each
individual send_*_sms() call site (see bookings/emails.py) wraps its own call in try/except,
the same way every send_*_email() function already does, so a broken SMS gateway never blocks
the booking action it's attached to.

Sandbox vs. production isn't a separate setting here - it's Africa's Talking's own convention:
the username 'sandbox' always resolves to their sandbox environment and a different base URL: a
real registered app uses its own username and goes live automatically.
"""
import requests
from decouple import config

SANDBOX_USERNAME = 'sandbox'


def send_sms(phone_number, message):
    """phone_number is expected in this app's own stored format (254XXXXXXXXX, no leading '+')
    but normalizes defensively either way, since nothing at the model level actually enforces
    that shape - see core.tests for the phone number format audit."""
    username = config('AFRICASTALKING_USERNAME')
    api_key = config('AFRICASTALKING_API_KEY')
    sender_id = config('AFRICASTALKING_SENDER_ID', default='')

    base_url = (
        'https://api.sandbox.africastalking.com' if username == SANDBOX_USERNAME
        else 'https://api.africastalking.com'
    )
    normalized_number = phone_number.strip().lstrip('+')
    payload = {
        'username': username,
        'to': f'+{normalized_number}',
        'message': message,
    }
    if sender_id:
        payload['from'] = sender_id

    response = requests.post(
        f'{base_url}/version1/messaging',
        data=payload,
        headers={'apiKey': api_key, 'Accept': 'application/json'},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
