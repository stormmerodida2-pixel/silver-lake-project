"""
Safaricom Daraja API client for M-Pesa STK Push and B2C payouts.

STK Push (customer-facing) requires these env vars (see .env.example) once you have Daraja app
credentials: MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_SHORTCODE, MPESA_PASSKEY,
MPESA_CALLBACK_URL, MPESA_CALLBACK_SECRET
Sandbox docs: https://developer.safaricom.co.ke/APIs/MpesaExpressSimulate

B2C (paying drivers/FleetPartners out - see payments.services.initiate_payout_disbursement) is a
separate Daraja product with its own "Go Live" application and credentials: MPESA_B2C_SHORTCODE,
MPESA_B2C_INITIATOR_NAME, MPESA_B2C_SECURITY_CREDENTIAL, MPESA_B2C_CALLBACK_URL. Entirely optional
- leave unset and payouts just stay on the existing manual Mark Paid flow.
Sandbox docs: https://developer.safaricom.co.ke/APIs/BusinessToCustomer
"""
import base64
from datetime import datetime

import requests
from decouple import config

MPESA_ENV = config('MPESA_ENV', default='sandbox')
BASE_URL = 'https://sandbox.safaricom.co.ke' if MPESA_ENV == 'sandbox' else 'https://api.safaricom.co.ke'


def get_access_token():
    consumer_key = config('MPESA_CONSUMER_KEY')
    consumer_secret = config('MPESA_CONSUMER_SECRET')
    response = requests.get(
        f'{BASE_URL}/oauth/v1/generate?grant_type=client_credentials',
        auth=(consumer_key, consumer_secret),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()['access_token']


def initiate_stk_push(phone_number, amount, account_reference, transaction_desc):
    shortcode = config('MPESA_SHORTCODE')
    passkey = config('MPESA_PASSKEY')
    # The secret is appended here rather than baked into MPESA_CALLBACK_URL directly, since
    # .env files don't support variable interpolation - this keeps the two independently
    # configurable while still landing on the same secret-guarded callback path.
    callback_secret = config('MPESA_CALLBACK_SECRET', default='')
    callback_url = f"{config('MPESA_CALLBACK_URL').rstrip('/')}/{callback_secret}/"

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = base64.b64encode(f'{shortcode}{passkey}{timestamp}'.encode()).decode()

    payload = {
        'BusinessShortCode': shortcode,
        'Password': password,
        'Timestamp': timestamp,
        'TransactionType': 'CustomerPayBillOnline',
        'Amount': int(amount),
        'PartyA': phone_number,
        'PartyB': shortcode,
        'PhoneNumber': phone_number,
        'CallBackURL': callback_url,
        'AccountReference': account_reference,
        'TransactionDesc': transaction_desc,
    }

    response = requests.post(
        f'{BASE_URL}/mpesa/stkpush/v1/processrequest',
        json=payload,
        headers={'Authorization': f'Bearer {get_access_token()}'},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def initiate_b2c_payment(phone_number, amount, remarks, occasion=''):
    """Business-to-Customer disbursement - SilverLake paying a driver/FleetPartner their share of
    a booking straight to their M-Pesa number, instead of a staff member wiring it by hand and
    clicking Mark Paid. Raises decouple.UndefinedValueError if the B2C-specific env vars below
    aren't set - callers (payments.services.initiate_payout_disbursement) turn that into a
    friendly "not configured yet, use Mark Paid instead" message rather than a raw 500."""
    shortcode = config('MPESA_B2C_SHORTCODE')
    initiator_name = config('MPESA_B2C_INITIATOR_NAME')
    security_credential = config('MPESA_B2C_SECURITY_CREDENTIAL')
    callback_secret = config('MPESA_CALLBACK_SECRET', default='')
    result_url = f"{config('MPESA_B2C_CALLBACK_URL').rstrip('/')}/{callback_secret}/"

    payload = {
        'InitiatorName': initiator_name,
        'SecurityCredential': security_credential,
        'CommandID': 'BusinessPayment',
        'Amount': int(amount),
        'PartyA': shortcode,
        'PartyB': phone_number,
        'Remarks': remarks[:100],
        # Safaricom requires both, even though this project treats a timeout the same as any
        # other failure (see payments.views.mpesa_b2c_result) - one handler serves both.
        'QueueTimeOutURL': result_url,
        'ResultURL': result_url,
        'Occasion': occasion[:100],
    }

    response = requests.post(
        f'{BASE_URL}/mpesa/b2c/v1/paymentrequest',
        json=payload,
        headers={'Authorization': f'Bearer {get_access_token()}'},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()
