import hmac

from decouple import config
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from bookings.models import Booking

from .models import Payment, PaymentStatus
from .serializers import PublicBookingPaymentSerializer, PaymentSerializer, StkPushRequestSerializer, TokenStkPushRequestSerializer
from .services import PaymentValidationError, initiate_stk_push_payment


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAdminUser]


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def stk_push(request):
    """Kick off an M-Pesa STK Push prompt on the customer's phone for a booking."""
    serializer = StkPushRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    booking = data['booking']
    if booking.user_id != request.user.id and not request.user.is_staff:
        return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)

    try:
        payment, result = initiate_stk_push_payment(booking, data['phone_number'], data['amount'])
    except PaymentValidationError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'payment_id': payment.id, **result}, status=status.HTTP_202_ACCEPTED)


stk_push.cls.throttle_scope = 'mpesa-stk'


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([ScopedRateThrottle])
def token_payment_detail(request, token):
    """No-login payment page for a booking - shared with a walk-up client via customer_token
    instead of requiring them to register/log in."""
    booking = get_object_or_404(Booking, customer_token=token)
    return Response(PublicBookingPaymentSerializer(booking).data)


token_payment_detail.cls.throttle_scope = 'token-payment-view'


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([ScopedRateThrottle])
def token_stk_push(request, token):
    """Same STK Push flow as `stk_push`, but reached via the no-login customer_token link -
    throttled tighter than most public endpoints, since each request can trigger a real M-Pesa
    prompt on a stranger's phone if this link ever leaked."""
    booking = get_object_or_404(Booking, customer_token=token)

    serializer = TokenStkPushRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    try:
        payment, result = initiate_stk_push_payment(booking, data['phone_number'], data['amount'])
    except PaymentValidationError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'payment_id': payment.id, **result}, status=status.HTTP_202_ACCEPTED)


token_stk_push.cls.throttle_scope = 'mpesa-stk'


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def mpesa_callback(request, secret):
    """Daraja calls this URL with the STK Push result. Configure MPESA_CALLBACK_URL to point here,
    with the secret path segment included - Safaricom doesn't sign these callbacks, and the
    CheckoutRequestID they're keyed on is also returned to the customer's own browser when the
    STK push is initiated, so without this secret anyone could forge a "payment succeeded"
    callback for a booking they never actually paid for."""
    expected_secret = config('MPESA_CALLBACK_SECRET', default='')
    if not expected_secret or not hmac.compare_digest(secret, expected_secret):
        return Response(status=status.HTTP_404_NOT_FOUND)

    body = request.data.get('Body', {}).get('stkCallback', {})
    checkout_request_id = body.get('CheckoutRequestID')
    result_code = body.get('ResultCode')

    try:
        payment = Payment.objects.get(mpesa_checkout_request_id=checkout_request_id)
    except Payment.DoesNotExist:
        return Response(status=status.HTTP_200_OK)

    if result_code == 0:
        items = {item['Name']: item.get('Value') for item in body.get('CallbackMetadata', {}).get('Item', [])}
        payment.status = PaymentStatus.SUCCESSFUL
        payment.mpesa_receipt_number = items.get('MpesaReceiptNumber', '')
        payment.save()
        payment.booking.confirm_if_deposit_met()
    else:
        payment.status = PaymentStatus.FAILED
        payment.save()

    return Response(status=status.HTTP_200_OK)
