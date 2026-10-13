"""The letterhead contact block comes from settings, not from the source code."""

from django.template import Context, Template


def test_the_report_footer_reads_the_contact_from_settings(settings):
    settings.REPORT_CONTACT_ADDRESS = "Calle Real 1, Ciudad"
    settings.REPORT_CONTACT_WEB = "www.empresa.example"
    settings.REPORT_CONTACT_PHONE = "+56 2 1111 1111"
    settings.REPORT_CONTACT_EMAIL = "hola@empresa.example"
    html = Template('{% include "reporting/_foot.html" %}').render(
        Context(
            {
                "section": "cover",
                "cover": True,
                "revision_label": "Rev A",
                "page": 1,
                "pages": 5,
            }
        )
    )
    for expected in (
        "Calle Real 1, Ciudad",
        "www.empresa.example",
        "+56 2 1111 1111",
        "hola@empresa.example",
    ):
        assert expected in html
