"""
Safaricom Daraja API client for M-Pesa STK Push.

Requires these env vars (see .env.example) once you have Daraja app credentials:
MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_SHORTCODE, MPESA_PASSKEY,
MPESA_CALLBACK_URL, MPESA_CALLBACK_SECRET
Sandbox docs: https://developer.safaricom.co.ke/APIs/MpesaExpressSimulate
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
