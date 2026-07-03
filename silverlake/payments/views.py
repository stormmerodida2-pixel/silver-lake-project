from rest_framework import permissions, status, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from . import mpesa
from .models import Payment, PaymentMethod, PaymentStatus
from .serializers import PaymentSerializer, StkPushRequestSerializer


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAdminUser]


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def stk_push(request):
    """Kick off an M-Pesa STK Push prompt on the customer's phone for a booking."""
    serializer = StkPushRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    booking = data['booking']
    if booking.user_id != request.user.id and not request.user.is_staff:
        return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)

    if data['amount'] > booking.balance_due:
        return Response(
            {'detail': f'Amount exceeds the outstanding balance of {booking.balance_due}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not booking.is_deposit_paid and data['amount'] < booking.deposit_amount:
        return Response(
            {'detail': f'First payment must be at least the deposit of {booking.deposit_amount}.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    payment = Payment.objects.create(
        booking=data['booking'],
        method=PaymentMethod.MPESA,
        amount=data['amount'],
        phone_number=data['phone_number'],
    )

    try:
        result = mpesa.initiate_stk_push(
            phone_number=data['phone_number'],
            amount=data['amount'],
            account_reference=f'SILVERLAKE-{payment.booking_id}',
            transaction_desc='SilverLake Car Rentals booking payment',
        )
    except Exception as exc:
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=['status'])
        return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    payment.mpesa_checkout_request_id = result.get('CheckoutRequestID', '')
    payment.save(update_fields=['mpesa_checkout_request_id'])

    return Response({'payment_id': payment.id, **result}, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def mpesa_callback(request):
    """Daraja calls this URL with the STK Push result. Configure MPESA_CALLBACK_URL to point here."""
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
