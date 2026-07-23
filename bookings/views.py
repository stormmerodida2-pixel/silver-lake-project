from datetime import date

from django.core.exceptions import ValidationError
from django.db import OperationalError, transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import generics, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import get_user_organization
from core.utils import capture_replaced_files, delete_files, parse_amount
from fleet.models import Vehicle
from reviews.models import Review
from reviews.serializers import BookingReviewCreateSerializer

from .models import Booking, BookingStatus
from .serializers import BookingSerializer


class BookingViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Requires login. Customers only see/manage their own bookings; a genuine SilverLake staff
    account sees all; a FleetPartner's own org staff only sees bookings on their own vehicles.

    Deliberately no destroy - a booking's payments/payouts/refund would cascade-delete with it,
    silently destroying financial history. "Removing" a booking is always cancel(), which keeps
    the record and its money trail intact."""

    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_staff:
            return Booking.objects.filter(user=user)
        organization = get_user_organization(user)
        if organization is None:
            return Booking.objects.all()
        return Booking.objects.filter(vehicle__owner=organization)

    def create(self, request, *args, **kwargs):
        """BookingSerializer.validate() checks for an overlapping booking on the same vehicle,
        but that check and the actual insert aren't atomic on their own - two requests for the
        same vehicle arriving close together (e.g. a popular car, or a double-submit) could both
        pass the conflict check before either booking exists, creating two confirmed bookings for
        the same car on the same dates.

        select_for_update() would be the standard fix, but it's a documented no-op on SQLite -
        Django's compiler silently drops the FOR UPDATE clause when the backend doesn't support
        row locking, so it provides zero protection there. Instead, force a real write against
        the vehicle row as the first statement in the transaction: a second concurrent request
        touching the same vehicle has to wait for this one to commit or roll back before its own
        conflict check can even run. On SQLite this locks the whole database (coarser - any
        concurrent write anywhere briefly waits, not just ones for this vehicle) since that's all
        SQLite offers; on MySQL (see settings/production.py's DATABASE_URL branch) InnoDB takes a
        real per-row lock on that same UPDATE instead, which is actually more precise. Either
        way, no different code path is needed for either database.

        A competing transaction that doesn't free the lock in time raises OperationalError -
        SQLite via DATABASES['default']['OPTIONS']['timeout'], MySQL via innodb_lock_wait_timeout
        (error 1205) - translate that into a clean, retryable 409 instead of a raw 500."""
        vehicle_id = request.data.get('vehicle')
        try:
            with transaction.atomic():
                if vehicle_id:
                    try:
                        Vehicle.objects.filter(pk=vehicle_id).update(updated_at=timezone.now())
                    except (ValueError, TypeError):
                        pass  # malformed id - let normal serializer validation produce a clean 400
                return super().create(request, *args, **kwargs)
        except OperationalError:
            return Response(
                {'detail': 'This vehicle is being booked by someone else right now. Please try again.'},
                status=status.HTTP_409_CONFLICT,
            )

    def perform_create(self, serializer):
        booking = serializer.save(user=self.request.user)

        from notifications.models import NotificationEvent
        from notifications.services import notify

        if booking.driver_id:
            from .emails import send_driver_booking_notification, send_driver_booking_sms

            send_driver_booking_notification(booking)
            send_driver_booking_sms(booking)
            notify(
                NotificationEvent.DRIVER_BOOKED,
                f'{booking.customer_name} booked you for {booking.vehicle.name} - {booking.rental_days} day(s)',
                driver=booking.driver, link_path='/driver',
            )

        notify(
            NotificationEvent.BOOKING_CREATED,
            f'{booking.vehicle.name} booked by {booking.customer_name} for {booking.rental_days} day(s)',
            organization=booking.vehicle.owner, link_path='/admin/bookings',
        )

    def perform_update(self, serializer):
        # A customer can PATCH their own booking to (re)upload a corrected license/ID document -
        # capture what's being replaced before save() so the old file gets cleaned up, not just
        # orphaned in storage forever.
        old_files = capture_replaced_files(serializer, ['customer_license_document', 'customer_id_document'])
        serializer.save()
        delete_files(old_files)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Lets a customer cancel their own booking (or staff, any booking). Staff can also flag
        driver_at_fault - the driver went unavailable or delayed without notice, through no
        fault of the client's - which forces a full refund even if the driver had already
        acknowledged the trip (see Booking.mark_cancelled for the refund-percentage rule). Not
        self-service: a client cancelling their own booking has no way to know why their driver
        went quiet, so this flag is silently ignored for anyone who isn't staff."""
        booking = self.get_object()
        driver_at_fault = bool(request.data.get('driver_at_fault')) and request.user.is_staff
        try:
            booking.mark_cancelled(driver_at_fault=driver_at_fault)
        except ValidationError as exc:
            return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['post'])
    def change_dates(self, request, pk=None):
        """Lets a customer adjust their own PENDING/CONFIRMED booking's dates in place, instead
        of cancelling and rebooking - see Booking.change_dates for why that's worth avoiding."""
        booking = self.get_object()
        try:
            new_start_date = date.fromisoformat(request.data.get('start_date') or '')
            new_end_date = date.fromisoformat(request.data.get('end_date') or '')
        except ValueError:
            return Response({'detail': 'A valid start_date and end_date are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            booking.change_dates(new_start_date, new_end_date)
        except ValidationError as exc:
            return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking).data)

    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        """Lets a customer leave a review (of the driver/service) for their own completed trip -
        one review per booking, only once it's actually completed."""
        booking = self.get_object()
        if booking.status != BookingStatus.COMPLETED:
            return Response(
                {'detail': 'You can only review a trip once it has been completed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if getattr(booking, 'review', None) is not None:
            return Response({'detail': 'You have already reviewed this trip.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = BookingReviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        Review.objects.create(
            booking=booking,
            driver=booking.driver,
            customer_name=booking.customer_name,
            **serializer.validated_data,
        )
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def receipt(self, request, pk=None):
        """A downloadable PDF receipt - only offered once at least one payment has actually
        succeeded (a booking nobody has paid anything toward has nothing to receipt). Scoped
        through the same get_object()/get_queryset() as the rest of this viewset - a customer
        only ever gets their own, staff get their own organization's (or everyone's, if
        platform-wide)."""
        booking = self.get_object()
        if booking.amount_paid <= 0:
            return Response(
                {'detail': 'No payment has been recorded for this booking yet.'}, status=status.HTTP_400_BAD_REQUEST,
            )

        from .receipts import generate_receipt_pdf

        pdf_bytes = generate_receipt_pdf(booking)
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="SilverLake-Receipt-{booking.id}.pdf"'
        return response

    @action(detail=True, methods=['get'])
    def location(self, request, pk=None):
        """Lets a customer see their own vehicle's live position - the same "trip is actually
        active" window DriverBookingLocationView requires before a driver is allowed to report
        one, so this never shows a stale pin from a past trip or a booking that hasn't started."""
        booking = self.get_object()
        vehicle = booking.vehicle
        today = timezone.localdate()
        trip_active = (
            booking.status in (BookingStatus.CONFIRMED, BookingStatus.ONGOING)
            and booking.start_date <= today <= booking.end_date
        )
        if not trip_active or not vehicle.last_location_lat:
            return Response({'tracking_available': False})
        return Response({
            'tracking_available': True,
            'last_location_lat': vehicle.last_location_lat,
            'last_location_lng': vehicle.last_location_lng,
            'last_location_at': vehicle.last_location_at,
            'vehicle_name': vehicle.name,
            'driver_name': booking.driver.full_name if booking.driver else None,
        })


from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from django.conf import settings

from accounts.services import get_or_create_customer_account
from drivers.permissions import IsDriverUser
from payments.models import Payment, PaymentMethod
from payments.serializers import MIN_BANK_TRANSFER_REFERENCE_LENGTH
from payments.services import (
    PaymentValidationError,
    confirm_offline_payment,
    declare_offline_payment,
    initiate_stk_push_payment,
    log_cash_deposit,
)

from .models import BookingSource
from .serializers import DriverOnsiteBookingSerializer, VehicleConditionReportSerializer
from .services import create_condition_report


class DriverOnsiteBookingCreateView(APIView):
    """Lets a driver create a booking on the spot for a walk-up client who won't be registering
    or logging in themselves - a lightweight customer account is created behind the scenes, and
    a no-login payment link is handed back for the driver to share with the client directly.

    Confirmed immediately rather than starting Pending-until-a-30%-deposit-lands like an online
    booking does - the deposit exists to get some commitment from a customer SilverLake has never
    met, but a walk-in client is standing right there with the driver, so that trust problem
    doesn't apply. In practice this means full payment is typically collected only once the trip
    itself is over (see Booking._complete_if_ended_and_paid, which already requires the full
    balance - not just a deposit - regardless of how a booking was created), and the client can
    start their trip immediately without paying anything upfront."""

    permission_classes = [IsDriverUser]

    def post(self, request):
        driver = request.user.driver_profile
        serializer = DriverOnsiteBookingSerializer(data=request.data, context={'driver': driver})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer, _ = get_or_create_customer_account(
            full_name=data['customer_name'], phone_number=data['customer_phone'], email=data['customer_email'],
        )

        booking = Booking(
            user=customer, vehicle=data['vehicle'], driver=driver, service_type='with_driver',
            source=BookingSource.DRIVER_ONSITE, status=BookingStatus.CONFIRMED,
            customer_name=data['customer_name'], customer_phone=data['customer_phone'],
            customer_email=data['customer_email'], pickup_location=data['pickup_location'],
            dropoff_location=data['dropoff_location'], start_date=data['start_date'],
            end_date=data['end_date'], notes=data['notes'],
            # The driver created this themselves, so there's nothing for them to be notified
            # about or acknowledge - unlike a booking an online customer places against them.
            driver_acknowledged_at=timezone.now(),
        )
        booking.save()

        from notifications.models import NotificationEvent
        from notifications.services import notify

        notify(
            NotificationEvent.BOOKING_CREATED,
            f'{booking.vehicle.name} booked by {booking.customer_name} for {booking.rental_days} day(s)',
            organization=booking.vehicle.owner, link_path='/admin/bookings',
        )

        return Response(
            {
                'booking': BookingSerializer(booking).data,
                'payment_url': f'{settings.FRONTEND_URL}/pay/{booking.customer_token}',
            },
            status=status.HTTP_201_CREATED,
        )


class DriverDeclarePaymentView(APIView):
    """Lets a driver, with a client physically present, record exactly how much the client says
    they're paying right now and by which method - cash, card, bank transfer, or M-Pesa. For
    M-Pesa this is just the existing STK Push flow triggered against the client's own phone -
    kept fully working here even while the driver portal's own frontend doesn't currently offer
    it as a button (see BookingPaymentCollector.vue's MPESA_ENABLED flag), so it's a one-line
    frontend change to bring back, not a backend one. For cash/card/bank transfer (see
    payments.services.declare_offline_payment) it creates a pending payment that gets separately
    confirmed once actually received - by the driver for cash/card (see
    DriverConfirmPaymentView), by staff for bank transfer (see
    core.views payments confirm-bank-transfer action) since there's no driver in that
    transaction to confirm it instead. The amount is locked in here, not re-entered at
    confirmation time."""

    permission_classes = [IsDriverUser]

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)

        method = request.data.get('method')
        try:
            amount = parse_amount(request.data.get('amount'))
        except ValueError:
            return Response({'detail': 'A valid amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

        note = ''
        if method == PaymentMethod.BANK_TRANSFER:
            note = str(request.data.get('reference', '')).strip()
            if len(note) < MIN_BANK_TRANSFER_REFERENCE_LENGTH:
                return Response(
                    {'detail': f'Enter the transaction reference (at least the last {MIN_BANK_TRANSFER_REFERENCE_LENGTH} digits/characters).'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            if method == PaymentMethod.MPESA:
                if not booking.customer_phone:
                    return Response({'detail': 'This booking has no phone number on file for M-Pesa.'}, status=status.HTTP_400_BAD_REQUEST)
                initiate_stk_push_payment(booking, booking.customer_phone, amount)
            else:
                declare_offline_payment(booking, method, amount, driver=driver, note=note)
        except PaymentValidationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BookingSerializer(booking).data)


class DriverConfirmPaymentView(APIView):
    """Lets a driver confirm a previously-declared cash/card payment was actually received (see
    DriverDeclarePaymentView / payments.services.confirm_offline_payment) - no amount here, it
    was already locked in when declared. Explicitly not for a bank transfer: a with-driver
    booking's customer can still declare one directly (see
    payments.views.token_declare_bank_transfer_payment / payments.views.declare_bank_transfer),
    which then also shows up in this same driver's booking.pending_payments - but the driver
    never actually sees that money, only staff checking the real bank statement can confirm it
    (see core.views payments confirm-bank-transfer action), so this rejects it explicitly rather
    than letting a driver vouch for funds they have no way to verify."""

    permission_classes = [IsDriverUser]

    def post(self, request, payment_id):
        driver = request.user.driver_profile
        payment = get_object_or_404(Payment, pk=payment_id, booking__driver=driver)

        if payment.method == PaymentMethod.BANK_TRANSFER:
            return Response(
                {'detail': 'A bank transfer can only be confirmed by staff, not the driver.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            confirm_offline_payment(payment)
        except PaymentValidationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BookingSerializer(payment.booking).data)


class DriverCashDepositView(APIView):
    """Lets a driver log that they've deposited cash they collected (see
    DriverConfirmPaymentView) into the company Paybill - the payout behind that cash payment
    can't be verified until this exists, and the deposited amount can never be less than what
    was collected (see payments.services.log_cash_deposit)."""

    permission_classes = [IsDriverUser]

    def post(self, request, payment_id):
        driver = request.user.driver_profile
        payment = get_object_or_404(Payment, pk=payment_id, booking__driver=driver)

        mpesa_reference = request.data.get('mpesa_reference', '')
        try:
            amount = parse_amount(request.data.get('amount'))
        except ValueError:
            return Response({'detail': 'A valid amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            log_cash_deposit(payment, amount, mpesa_reference, driver=driver)
        except PaymentValidationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # If this was the only thing holding the trip back (already ended, already fully paid),
        # completing it right now rather than waiting for some unrelated later event to
        # re-check - see Booking._complete_if_ended_and_paid.
        payment.booking.confirm_if_deposit_met()

        return Response(BookingSerializer(payment.booking).data)


class DriverBookingCompleteView(APIView):
    """Lets a driver mark one of their own trips completed once it's fully paid - the only other
    way to do this today is an admin manually changing the booking's status, which isn't
    something a driver out in the field can rely on. Sends the same review-invite email the
    admin-side completion does."""

    permission_classes = [IsDriverUser]

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)

        if booking.status == BookingStatus.CANCELLED:
            return Response({'detail': 'Cannot complete a cancelled trip.'}, status=status.HTTP_400_BAD_REQUEST)
        if booking.status == BookingStatus.COMPLETED:
            return Response({'detail': 'This trip is already completed.'}, status=status.HTTP_400_BAD_REQUEST)
        if not booking.is_government_contract and booking.balance_due > 0:
            return Response(
                {'detail': f'Cannot complete this trip - there is an outstanding balance of KES {booking.balance_due:,.2f}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if booking.has_undeposited_cash:
            return Response(
                {'detail': 'Cannot complete this trip - deposit the cash you collected on this booking into the Paybill first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A direct completion (skipping the explicit Start/End Trip buttons) still means the
        # trip physically happened - stamp trip_ended_at if it isn't already, so anyone later
        # checking "did this trip actually end" gets a real answer either way.
        if not booking.trip_ended_at:
            booking.trip_ended_at = timezone.now()
            booking.save(update_fields=['trip_ended_at'])

        booking.status = BookingStatus.COMPLETED
        booking.save(update_fields=['status'])
        # Normally already queued by confirm_if_deposit_met() once the balance cleared (get_or_create
        # makes this a harmless no-op then) - but a government contract's balance never clears
        # through that path, so this is the only place its payout actually gets queued.
        booking._ensure_driver_payout()

        from .emails import send_trip_completed_email

        send_trip_completed_email(booking)

        return Response(BookingSerializer(booking).data)


class DriverBookingStartTripView(APIView):
    """Lets a driver confirm a trip has actually begun (vehicle handed over) - the only real
    signal of this today is the driver's own say-so, not payment status or dates."""

    permission_classes = [IsDriverUser]

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)
        try:
            booking.start_trip()
        except ValidationError as exc:
            return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking).data)


class DriverBookingEndTripView(APIView):
    """Lets a driver confirm the vehicle has been physically returned. If the trip happens to
    already be fully paid, this completes it immediately; otherwise it stays open until the
    balance clears (see Booking.end_trip)."""

    permission_classes = [IsDriverUser]

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)
        try:
            booking.end_trip()
        except ValidationError as exc:
            return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)
        return Response(BookingSerializer(booking).data)


class DriverBookingLocationView(APIView):
    """Lets a driver report their vehicle's current GPS position while a trip is actually in
    progress - reported by the driver's own browser (no separate hardware), so it only works
    while they have the portal open. Only the latest fix is kept (on the vehicle, not a history
    table); the admin fleet map reads it from there."""

    permission_classes = [IsDriverUser]

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)

        today = timezone.localdate()
        if booking.status not in (BookingStatus.CONFIRMED, BookingStatus.ONGOING):
            return Response(
                {'detail': 'This trip is not currently active.'}, status=status.HTTP_400_BAD_REQUEST,
            )
        if not (booking.start_date <= today <= booking.end_date):
            return Response(
                {'detail': "This trip's dates are not currently active."}, status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lat = float(request.data.get('lat'))
            lng = float(request.data.get('lng'))
        except (TypeError, ValueError):
            return Response({'detail': 'A valid lat and lng are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return Response({'detail': 'lat/lng out of range.'}, status=status.HTTP_400_BAD_REQUEST)

        vehicle = booking.vehicle
        vehicle.last_location_lat = lat
        vehicle.last_location_lng = lng
        vehicle.last_location_at = timezone.now()
        vehicle.save(update_fields=['last_location_lat', 'last_location_lng', 'last_location_at'])

        return Response({
            'last_location_lat': vehicle.last_location_lat,
            'last_location_lng': vehicle.last_location_lng,
            'last_location_at': vehicle.last_location_at,
        })


class DriverBookingListView(generics.ListAPIView):
    """A driver's own assigned bookings - both ones an online customer placed against them and
    their own walk-up ones - so they can see what's coming up and acknowledge new ones."""

    serializer_class = BookingSerializer
    permission_classes = [IsDriverUser]

    def get_queryset(self):
        driver = self.request.user.driver_profile
        return Booking.objects.filter(driver=driver).exclude(status=BookingStatus.CANCELLED)


class DriverBookingAcknowledgeView(APIView):
    """Lets a driver acknowledge a booking an online customer placed against them. Purely
    informational - doesn't gate confirmation or payment, just lets the driver mark that
    they've seen it."""

    permission_classes = [IsDriverUser]

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)
        if not booking.driver_acknowledged_at:
            booking.driver_acknowledged_at = timezone.now()
            booking.save(update_fields=['driver_acknowledged_at'])

            from notifications.models import NotificationEvent
            from notifications.services import notify

            notify(
                NotificationEvent.DRIVER_ACKNOWLEDGED,
                f'{driver.full_name} acknowledged booking #{booking.pk} for {booking.customer_name}',
                organization=booking.vehicle.owner, link_path='/admin/bookings',
            )
        return Response(BookingSerializer(booking).data)


class DriverConditionReportView(APIView):
    """Lets a driver view and log the vehicle's condition (odometer, fuel level, notes, photos)
    at pickup or return for one of their own bookings - see VehicleConditionReport for why this
    is optional, never required to Start/End Trip."""

    permission_classes = [IsDriverUser]

    def get(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)
        reports = booking.condition_reports.all()
        return Response(VehicleConditionReportSerializer(reports, many=True, context={'request': request}).data)

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)

        try:
            report = create_condition_report(
                booking, request.data.get('report_type'), request.data.get('mileage'),
                request.data.get('fuel_level', ''), request.data.get('notes', ''),
                request.FILES.getlist('photos'), logged_by=driver,
            )
        except ValidationError as exc:
            return Response({'detail': exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            VehicleConditionReportSerializer(report, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


