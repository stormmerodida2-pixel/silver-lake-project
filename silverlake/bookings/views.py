from django.core.exceptions import ValidationError
from django.db import OperationalError, transaction
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

        select_for_update() would be the standard fix, but it's a documented no-op on SQLite
        (this project's current database) - Django's compiler silently drops the FOR UPDATE
        clause when the backend doesn't support row locking, so it provides zero protection
        here. Instead, force a real write against the vehicle row as the first statement in the
        transaction: SQLite acquires a database-level write lock on the first write in a
        transaction, so a second concurrent request touching the database has to wait for this
        one to commit or roll back before its own conflict check can even run. This is coarser
        than real row-level locking (any concurrent write anywhere briefly waits, not just ones
        for this vehicle) but it's correct, and it's what actually works on SQLite. If this ever
        moves to Postgres, swap this for select_for_update(), which does provide real per-row
        locking there.

        SQLite raises OperationalError('database is locked') rather than blocking forever if a
        competing transaction doesn't free the lock within DATABASES['default']['OPTIONS']
        ['timeout'] - translate that into a clean, retryable 409 instead of a raw 500."""
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
        if booking.driver_id:
            from .emails import send_driver_booking_notification

            send_driver_booking_notification(booking)

    def perform_update(self, serializer):
        # A customer can PATCH their own booking to (re)upload a corrected license/ID document -
        # capture what's being replaced before save() so the old file gets cleaned up, not just
        # orphaned in storage forever.
        old_files = capture_replaced_files(serializer, ['customer_license_document', 'customer_id_document'])
        serializer.save()
        delete_files(old_files)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Lets a customer cancel their own booking (or staff, any booking)."""
        booking = self.get_object()
        try:
            booking.mark_cancelled()
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


from django.shortcuts import get_object_or_404
from rest_framework.views import APIView

from django.conf import settings
from django.utils import timezone

from accounts.services import get_or_create_customer_account
from drivers.permissions import IsDriverUser
from payments.models import Payment, PaymentMethod
from payments.services import (
    PaymentValidationError,
    confirm_offline_payment,
    declare_offline_payment,
    initiate_stk_push_payment,
    log_cash_deposit,
)

from .models import BookingSource
from .serializers import DriverOnsiteBookingSerializer


class DriverOnsiteBookingCreateView(APIView):
    """Lets a driver create a booking on the spot for a walk-up client who won't be registering
    or logging in themselves - a lightweight customer account is created behind the scenes, and
    a no-login payment link is handed back for the driver to share with the client directly."""

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
            source=BookingSource.DRIVER_ONSITE,
            customer_name=data['customer_name'], customer_phone=data['customer_phone'],
            customer_email=data['customer_email'], pickup_location=data['pickup_location'],
            dropoff_location=data['dropoff_location'], start_date=data['start_date'],
            end_date=data['end_date'], notes=data['notes'],
            # The driver created this themselves, so there's nothing for them to be notified
            # about or acknowledge - unlike a booking an online customer places against them.
            driver_acknowledged_at=timezone.now(),
        )
        booking.save()

        return Response(
            {
                'booking': BookingSerializer(booking).data,
                'payment_url': f'{settings.FRONTEND_URL}/pay/{booking.customer_token}',
            },
            status=status.HTTP_201_CREATED,
        )


class DriverDeclarePaymentView(APIView):
    """Lets a driver, with a client physically present, record exactly how much the client says
    they're paying right now and by which method - cash, card, or M-Pesa. For M-Pesa this is
    just the existing STK Push flow triggered against the client's own phone; for cash/card
    (see payments.services.declare_offline_payment) it creates a pending payment that the driver
    separately confirms once actually received (see DriverConfirmPaymentView) - the amount is
    locked in here, not re-entered at confirmation time."""

    permission_classes = [IsDriverUser]

    def post(self, request, pk):
        driver = request.user.driver_profile
        booking = get_object_or_404(Booking, pk=pk, driver=driver)

        method = request.data.get('method')
        try:
            amount = parse_amount(request.data.get('amount'))
        except ValueError:
            return Response({'detail': 'A valid amount is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if method == PaymentMethod.MPESA:
                if not booking.customer_phone:
                    return Response({'detail': 'This booking has no phone number on file for M-Pesa.'}, status=status.HTTP_400_BAD_REQUEST)
                initiate_stk_push_payment(booking, booking.customer_phone, amount)
            else:
                declare_offline_payment(booking, method, amount, driver=driver)
        except PaymentValidationError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BookingSerializer(booking).data)


class DriverConfirmPaymentView(APIView):
    """Lets a driver confirm a previously-declared cash/card payment was actually received (see
    DriverDeclarePaymentView / payments.services.confirm_offline_payment) - no amount here, it
    was already locked in when declared."""

    permission_classes = [IsDriverUser]

    def post(self, request, payment_id):
        driver = request.user.driver_profile
        payment = get_object_or_404(Payment, pk=payment_id, booking__driver=driver)

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
        if booking.balance_due > 0:
            return Response(
                {'detail': f'Cannot complete this trip - there is an outstanding balance of KES {booking.balance_due:,.2f}.'},
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
        return Response(BookingSerializer(booking).data)


