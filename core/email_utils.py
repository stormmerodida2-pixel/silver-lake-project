import email.message
import os

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

# The brand icon (medallion + car), embedded inline via Content-ID rather than linked as a
# remote URL - most email clients block remote images by default, but an inline attachment
# always renders. base_email.html's header references it as `<img src="cid:logo">`.
LOGO_PATH = os.path.join(os.path.dirname(__file__), 'static', 'emails', 'logo.png')


def _inline_logo_part():
    with open(LOGO_PATH, 'rb') as f:
        data = f.read()
    part = email.message.MIMEPart()
    part.set_content(data, 'image', 'png', filename='logo.png', cid='<logo>', disposition='inline')
    return part


def send_branded_email(subject, template_name, context, recipient_list=None, bcc=None):
    """Renders template_name (which should extend emails/base_email.html) to HTML,
    derives a plain-text fallback from it, and sends both via EmailMultiAlternatives with
    the brand logo attached inline.

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
    message.attach(_inline_logo_part())
    message.send()
