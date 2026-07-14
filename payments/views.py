import hmac
from datetime import timedelta

from decouple import config
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from bookings.models import Booking
from core.audit import log_admin_action
from core.permissions import IsSupportStaff, get_user_organization
from core.utils import parse_amount, search_filter

from .emails import send_cash_deposit_reminder_email, send_payment_reminder_email
from .models import Payment, PaymentMethod, PaymentStatus
from .serializers import PublicBookingPaymentSerializer, PaymentSerializer, StkPushRequestSerializer, TokenStkPushRequestSerializer
from .services import PaymentValidationError, declare_offline_payment, initiate_stk_push_payment

# How often staff can re-nudge the same driver about the same pending payment - long enough that
# a reminder isn't just spam, short enough that a driver who genuinely forgot can be re-poked
# same day.
REMINDER_COOLDOWN = timedelta(hours=1)


def _get_booking_by_token(token):
    """Shared lookup for every no-login customer_token endpoint below - treats an expired link
    (see Booking.customer_token_expires_at) the same as a nonexistent one, a 404, rather than a
    more specific status, so an old link doesn't reveal whether it was ever valid at all."""
    booking = get_object_or_404(Booking, customer_token=token)
    if booking.is_customer_token_expired:
        raise Http404('This link has expired.')
    return booking


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """Staff can browse the full payment log; any authenticated customer can poll a single
    payment's status by id to check whether their own STK push actually went through - list
    stays staff-only so nobody can browse other people's payments."""

    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer

    def get_permissions(self):
        if self.action == 'retrieve':
            return [permissions.IsAuthenticated()]
        return [permissions.IsAdminUser()]

    def get_queryset(self):
        organization = get_user_organization(self.request.user)
        queryset = self.queryset if organization is None else self.queryset.filter(booking__vehicle__owner=organization)

        params = self.request.query_params
        queryset = search_filter(
            queryset, params.get('search', '').strip(),
            ['mpesa_receipt_number', 'card_transaction_ref', 'booking__customer_name'],
        )
        method = params.get('method', '').strip()
        if method:
            queryset = queryset.filter(method=method)
        payment_status = params.get('status', '').strip()
        if payment_status:
            queryset = queryset.filter(status=payment_status)
        return queryset

    def get_object(self):
        obj = super().get_object()
        if not self.request.user.is_staff and obj.booking.user_id != self.request.user.id:
            raise Http404
        return obj

    @action(detail=True, methods=['post'], permission_classes=[IsSupportStaff])
    def remind(self, request, pk=None):
        """Nudges the driver who's sitting on an unconfirmed payment - the client (or the driver
        themselves) declared it, but nothing counts toward the booking's balance until the
        driver actually confirms receiving it, and there's otherwise no prompt for them to do
        that beyond checking their own portal. Any staff account can do this (support staff or
        superadmin) - it's just an email nudge, not a destructive or financial action."""
        payment = self.get_object()
        if payment.status != PaymentStatus.PENDING:
            return Response({'detail': 'Only a pending payment can be reminded about.'}, status=status.HTTP_400_BAD_REQUEST)
        if not payment.recorded_by_driver_id:
            return Response({'detail': 'This payment has no driver to remind.'}, status=status.HTTP_400_BAD_REQUEST)
        if payment.last_reminded_at and timezone.now() - payment.last_reminded_at < REMINDER_COOLDOWN:
            return Response({'detail': 'A reminder was already sent recently. Please wait before sending another.'}, status=status.HTTP_400_BAD_REQUEST)

        payment.last_reminded_at = timezone.now()
        payment.save(update_fields=['last_reminded_at'])
        send_payment_reminder_email(payment)
        log_admin_action(request, 'payment.remind', payment)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.PAYMENT_REMINDER, f'Please confirm the {payment.get_method_display()} payment you declared',
            driver=payment.recorded_by_driver, link_path='/driver',
        )
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=['post'], url_path='remind-deposit', permission_classes=[IsSupportStaff])
    def remind_deposit(self, request, pk=None):
        """Nudges the driver who's collected cash but hasn't yet redeposited it into the company
        Paybill (see payments.services.log_cash_deposit) - distinct from `remind` above, which is
        about confirming receipt in the first place. Any staff account can do this."""
        payment = self.get_object()
        if payment.method != PaymentMethod.CASH or payment.status != PaymentStatus.SUCCESSFUL:
            return Response({'detail': 'Only a confirmed cash payment can be reminded about a deposit.'}, status=status.HTTP_400_BAD_REQUEST)
        if hasattr(payment, 'cash_deposit'):
            return Response({'detail': 'This cash payment has already been deposited.'}, status=status.HTTP_400_BAD_REQUEST)
        if not payment.recorded_by_driver_id:
            return Response({'detail': 'This payment has no driver to remind.'}, status=status.HTTP_400_BAD_REQUEST)
        if payment.last_reminded_at and timezone.now() - payment.last_reminded_at < REMINDER_COOLDOWN:
            return Response({'detail': 'A reminder was already sent recently. Please wait before sending another.'}, status=status.HTTP_400_BAD_REQUEST)

        payment.last_reminded_at = timezone.now()
        payment.save(update_fields=['last_reminded_at'])
        send_cash_deposit_reminder_email(payment)
        log_admin_action(request, 'payment.remind_deposit', payment)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.CASH_DEPOSIT_REMINDER, 'Please redeposit the cash you collected into the Paybill',
            driver=payment.recorded_by_driver, link_path='/driver',
        )
        return Response(self.get_serializer(payment).data)

    @action(detail=True, methods=['post'], url_path='resolve-dispute', permission_classes=[IsSupportStaff])
    def resolve_dispute(self, request, pk=None):
        """Clears a customer's dispute on a cash payment once staff have investigated and
        reconciled it - requires a note describing how, the same attested-action pattern as
        AdminDriverPayoutViewSet.verify, so clearing a dispute always leaves a trail of how it
        was resolved. Deliberately doesn't touch the payout's own verification state - re-
        verifying a payout is a separate, deliberate attestation with its own note (see
        DriverPayout.verify), not something clearing a dispute should imply automatically."""
        payment = self.get_object()
        if not payment.is_disputed:
            return Response({'detail': 'This payment is not currently disputed.'}, status=status.HTTP_400_BAD_REQUEST)
        note = request.data.get('note', '').strip()
        if not note:
            return Response(
                {'note': ['Describe how this dispute was resolved.']}, status=status.HTTP_400_BAD_REQUEST,
            )

        payment.is_disputed = False
        payment.dispute_resolution_note = note
        payment.dispute_resolved_at = timezone.now()
        payment.save(update_fields=['is_disputed', 'dispute_resolution_note', 'dispute_resolved_at'])
        log_admin_action(request, 'payment.resolve_dispute', payment, detail=note)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.DISPUTE_RESOLVED, f'Dispute resolved for booking #{payment.booking_id}',
            organization=payment.booking.vehicle.owner, link_path='/admin/payments',
        )
        return Response(self.get_serializer(payment).data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
@throttle_classes([ScopedRateThrottle])
def stk_push(request):
    """Kick off an M-Pesa STK Push prompt on the customer's phone for a booking. Unlike every
    other admin-facing endpoint, this one resolves its booking straight from the request body
    (StkPushRequestSerializer's unscoped Booking.objects.all()) rather than through an org-scoped
    get_queryset(), so the org check has to happen here explicitly - otherwise any is_staff
    account, including a FleetPartner's own org-admin, could trigger a real charge attempt
    against a booking belonging to a different organization entirely."""
    serializer = StkPushRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    booking = data['booking']
    if booking.user_id != request.user.id:
        if not request.user.is_staff:
            return Response({'detail': 'Not your booking.'}, status=status.HTTP_403_FORBIDDEN)
        organization = get_user_organization(request.user)
        if organization is not None and booking.vehicle.owner_id != organization.id:
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
    booking = _get_booking_by_token(token)
    return Response(PublicBookingPaymentSerializer(booking).data)


token_payment_detail.cls.throttle_scope = 'token-payment-view'


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([ScopedRateThrottle])
def token_stk_push(request, token):
    """Same STK Push flow as `stk_push`, but reached via the no-login customer_token link -
    throttled tighter than most public endpoints, since each request can trigger a real M-Pesa
    prompt on a stranger's phone if this link ever leaked."""
    booking = _get_booking_by_token(token)

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
@throttle_classes([ScopedRateThrottle])
def token_declare_cash_payment(request, token):
    """Lets the client themselves declare they're paying in cash, from the same no-login page
    used for M-Pesa - the self-service equivalent of a driver typing the amount on the client's
    behalf (see bookings.views.DriverDeclarePaymentView). Only valid for a with-driver booking:
    cash is handed to the assigned driver in person, so there's no one to eventually confirm
    receiving it without one. This only records what the client says they're paying - the
    driver still has to separately confirm they actually received it (see
    bookings.views.DriverConfirmPaymentView) before it counts toward the balance."""
    booking = _get_booking_by_token(token)
    if not booking.driver_id:
        return Response(
            {'detail': 'This booking has no driver assigned to hand cash to.'}, status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        amount = parse_amount(request.data.get('amount'))
    except ValueError:
        return Response({'detail': 'A valid amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        declare_offline_payment(booking, PaymentMethod.CASH, amount, driver=booking.driver)
    except PaymentValidationError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return Response(PublicBookingPaymentSerializer(booking).data, status=status.HTTP_201_CREATED)


token_declare_cash_payment.cls.throttle_scope = 'token-payment-view'


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
@throttle_classes([ScopedRateThrottle])
def token_payment_status(request, token, payment_id):
    """Lets the no-login payment page poll whether its STK push actually went through -
    scoped to the booking's own customer_token so a payment id alone isn't enough to look up
    someone else's payment."""
    booking = _get_booking_by_token(token)
    payment = get_object_or_404(Payment, pk=payment_id, booking=booking)
    return Response({'status': payment.status})


token_payment_status.cls.throttle_scope = 'token-payment-view'


@api_view(['GET', 'POST'])
@permission_classes([permissions.AllowAny])
@throttle_classes([ScopedRateThrottle])
def token_dispute_payment(request, token, payment_id):
    """The one independent check on a driver's self-reported cash payment - reached via the
    no-login link in the cash_payment_recorded email, since the customer who actually handed
    over (or didn't hand over) the cash is the only one who can say the recorded amount is
    wrong. GET lets the dispute page show what's being disputed before the customer submits
    anything; POST files the dispute.

    Only cash payments are disputable - M-Pesa/card payments are independently confirmed by
    their own gateway already, so there's nothing for a customer-side dispute to add there.

    Filing a dispute re-locks the booking's payout (if one exists and isn't paid yet) by
    forcing needs_verification/is_verified back to their pre-verification state, even if a
    superadmin had already verified it - a dispute arriving after verification means that
    verification needs to be redone, not that it still stands."""
    booking = _get_booking_by_token(token)
    payment = get_object_or_404(Payment, pk=payment_id, booking=booking, method=PaymentMethod.CASH)

    if request.method == 'GET':
        return Response({
            'amount': payment.amount, 'created_at': payment.created_at,
            'is_disputed': payment.is_disputed, 'booking_id': booking.pk,
        })

    payment.is_disputed = True
    payment.disputed_at = timezone.now()
    payment.dispute_note = request.data.get('note', '')
    payment.save(update_fields=['is_disputed', 'disputed_at', 'dispute_note'])

    payout = getattr(booking, 'driver_payout', None)
    if payout and not payout.is_paid:
        payout.needs_verification = True
        payout.is_verified = False
        payout.save(update_fields=['needs_verification', 'is_verified'])

    from .emails import send_payment_disputed_staff_notification_email

    send_payment_disputed_staff_notification_email(payment)

    from notifications.models import NotificationEvent
    from notifications.services import notify

    notify(
        NotificationEvent.PAYMENT_DISPUTED, f'Payment disputed on booking #{booking.pk}',
        organization=booking.vehicle.owner, link_path='/admin/payments',
    )

    return Response({'detail': 'Dispute recorded. Our team will follow up with you.'})


token_dispute_payment.cls.throttle_scope = 'payment-dispute'


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
