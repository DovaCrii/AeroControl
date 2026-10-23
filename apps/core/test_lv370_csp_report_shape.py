"""LV-370: el receptor de informes CSP no revienta con un cuerpo de forma inesperada.

`/csp-report/` es público y sin CSRF (el navegador lo llama solo), así que su cuerpo es
entrada hostil. Una auditoría encontró que `{"csp-report": []}` daba un 500 (`.get` sobre
una lista). Aquí se fija que **cualquier** forma responde 204 y que solo se registran los
campos de un informe real.
"""

import json
import logging

import pytest
from django.urls import reverse

URL = "/csp-report/"
JSON = "application/json"


def _post(client, body):
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    return client.post(URL, data=data, content_type=JSON)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {"csp-report": []},
        {"csp-report": "texto"},
        {"csp-report": 42},
        {"csp-report": None},
        {"csp-report": [{"blocked-uri": "x"}]},
        {"csp-report": {"blocked-uri": ["lista"], "violated-directive": {"a": 1}}},
        [],
        ["csp-report"],
        "cadena",
        42,
        None,
        {},
        b"",
        b"no es json",
        b"\xff\xfe\x00",
        b"{" * 100,
    ],
)
def test_any_body_shape_answers_204_and_never_500(client, body):
    assert _post(client, body).status_code == 204


@pytest.mark.django_db
def test_a_real_report_logs_only_the_known_fields(client, caplog):
    body = {
        "csp-report": {
            "blocked-uri": "https://evil.example/x.js",
            "violated-directive": "script-src",
            "document-uri": "https://app.example/panel",
            "original-policy": "default-src 'self'; secreto-que-no-se-registra",
            "campo-extra": "tampoco",
        }
    }
    with caplog.at_level(logging.WARNING, logger="aerocontrol.csp"):
        assert _post(client, body).status_code == 204
    records = [r for r in caplog.records if r.name == "aerocontrol.csp"]
    assert len(records) == 1
    record = records[0]
    assert record.blocked_uri == "https://evil.example/x.js"
    assert record.violated_directive == "script-src"
    assert record.document_uri == "https://app.example/panel"
    assert not hasattr(record, "original_policy")
    assert "secreto-que-no-se-registra" not in caplog.text


@pytest.mark.django_db
def test_a_non_object_report_logs_an_empty_report(client, caplog):
    with caplog.at_level(logging.WARNING, logger="aerocontrol.csp"):
        assert _post(client, {"csp-report": []}).status_code == 204
    record = [r for r in caplog.records if r.name == "aerocontrol.csp"][0]
    assert record.blocked_uri == ""
    assert record.violated_directive == ""
    assert record.document_uri == ""


@pytest.mark.django_db
def test_the_body_is_still_capped(client, caplog):
    huge = {"csp-report": {"blocked-uri": "a" * 50_000}}
    with caplog.at_level(logging.WARNING, logger="aerocontrol.csp"):
        assert _post(client, huge).status_code == 204
    # el cuerpo se corta a 8 KB: el JSON queda incompleto y se trata como vacío
    record = [r for r in caplog.records if r.name == "aerocontrol.csp"][0]
    assert len(record.blocked_uri) <= 500


def test_the_route_is_the_one_the_policy_advertises():
    assert reverse("csp-report") == URL
