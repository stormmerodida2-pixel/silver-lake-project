from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def send_branded_email(subject, template_name, context, recipient_list=None, bcc=None):
    """Renders template_name (which should extend emails/base_email.html) to HTML,
    derives a plain-text fallback from it, and sends both via EmailMultiAlternatives.

    Use `bcc` instead of `recipient_list` when notifying multiple people (e.g. all staff)
    so they don't see each other's email addresses."""
    context = {**context, 'subject': subject}
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list or [],
        bcc=bcc or [],
    )
    message.attach_alternative(html_content, 'text/html')
    message.send()
