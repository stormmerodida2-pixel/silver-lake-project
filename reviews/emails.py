from django.conf import settings
from django.contrib.auth import get_user_model

from core.email_utils import send_branded_email

User = get_user_model()


def send_review_submitted_staff_notification_email(review):
    """Notifies every active staff account the moment a customer submits a review (see
    bookings.views.BookingViewSet.review) - it still needs admin moderation
    (Review.is_approved) before going public, but previously nothing told staff one existed at
    all, good or bad, until someone happened to open the moderation queue. A low rating in
    particular is worth a prompt look - it may be a real service failure worth a personal
    follow-up call, not just something to eventually approve or reject."""
    staff_emails = list(
        User.objects.filter(is_staff=True, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not staff_emails:
        return

    is_low_rating = review.rating <= 2
    subject_prefix = '⚠ Low rating' if is_low_rating else 'New review'
    send_branded_email(
        subject=f'{subject_prefix} submitted — {review.rating}/5 from {review.customer_name}',
        template_name='emails/review_submitted_staff_notification.html',
        context={
            'customer_name': review.customer_name,
            'rating': review.rating,
            'comment': review.comment,
            'is_low_rating': is_low_rating,
            'reviews_url': f'{settings.FRONTEND_URL}/admin/reviews',
        },
        recipient_list=[settings.DEFAULT_FROM_EMAIL],
        bcc=staff_emails,
    )
