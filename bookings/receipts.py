import os
from io import BytesIO

from django.template.loader import render_to_string
from django.utils import timezone
from xhtml2pdf import pisa

from core.email_utils import LOGO_PATH
from payments.models import PaymentStatus


def _link_callback(uri, rel):
    """Resolves the logo's local filesystem path for xhtml2pdf - its default resource fetcher
    doesn't reliably handle file:// URIs (a space anywhere in the path, as in this project's own
    directory name, breaks it), so this just hands the already-absolute path straight back."""
    if os.path.isabs(uri) and os.path.exists(uri):
        return uri
    return uri


def generate_receipt_pdf(booking):
    """Renders bookings/templates/receipts/booking_receipt.html to PDF bytes - only ever shows
    successful payments (a failed/pending M-Pesa attempt has no place on a receipt); a booking
    with none of those isn't offered a receipt at all (see BookingViewSet.receipt)."""
    payments = booking.payments.filter(status=PaymentStatus.SUCCESSFUL).order_by('created_at')
    html = render_to_string('receipts/booking_receipt.html', {
        'booking': booking,
        'vehicle': booking.vehicle,
        'payments': payments,
        'issued_at': timezone.now(),
        'logo_uri': LOGO_PATH,
    })

    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer, link_callback=_link_callback)
    return buffer.getvalue()
