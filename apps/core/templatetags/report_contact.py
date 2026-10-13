from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def report_contact():
    """The letterhead contact block, read from settings (see `REPORT_CONTACT_*`)."""
    return {
        "address": settings.REPORT_CONTACT_ADDRESS,
        "web": settings.REPORT_CONTACT_WEB,
        "phone": settings.REPORT_CONTACT_PHONE,
        "email": settings.REPORT_CONTACT_EMAIL,
    }
