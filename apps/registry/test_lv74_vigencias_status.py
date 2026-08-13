"""LV-74/LV-81: loading a vigencia must leave the filing status consistent.

Found in production on 2026-08-13, by looking at the data after the load rather
than by a test: `RPA-3696` came out with `insurance_expiry = 2026-12-21` and
`insurance_status = missing` at the same time -- a policy on file that the fiche
still described as missing.

The cause is a Django detail worth remembering: `save(update_fields=[...])` does
**not** run `clean()`, so the normalization that keeps those two fields honest
never fired. The rule lives on the model; the loader has to invoke it.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.registry.models import Aircraft, Operator

TODAY = timezone.localdate()


def _aircraft(registration="RPA-3696", **kwargs):
    return Aircraft.objects.create(
        registration=registration,
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **kwargs,
    )


def _csv(tmp_path, rows):
    path = tmp_path / "vigencias.csv"
    path.write_text(
        "kind,key,expiry\n" + "\n".join(",".join(row) for row in rows),
        encoding="utf-8",
    )
    return str(path)


@pytest.mark.django_db
class TestTheStatusFollowsTheDate:
    def test_loading_a_valid_date_stops_the_fiche_saying_missing(self, tmp_path):
        """The production case, as a test."""
        aircraft = _aircraft()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_MISSING
        future = TODAY + timedelta(days=120)

        call_command(
            "load_dgac_vigencias",
            "--file",
            _csv(tmp_path, [("aircraft", "RPA-3696", future.isoformat())]),
        )

        aircraft.refresh_from_db()
        assert aircraft.insurance_expiry == future
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE

    def test_a_date_already_in_the_past_leaves_it_missing(self, tmp_path):
        """A lapsed policy is exactly what "missing or to be renewed" means, so
        loading one must not flip the fiche to "in force"."""
        aircraft = _aircraft()
        past = TODAY - timedelta(days=5)

        call_command(
            "load_dgac_vigencias",
            "--file",
            _csv(tmp_path, [("aircraft", "RPA-3696", past.isoformat())]),
        )

        aircraft.refresh_from_db()
        assert aircraft.insurance_expiry == past
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_MISSING

    def test_a_filing_in_progress_survives_the_load(self, tmp_path):
        """Someone marked this one as being arranged; a date arriving from a
        capture must not overwrite that judgement (the renewal case LV-81 exists
        for)."""
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_FILED)
        future = TODAY + timedelta(days=90)

        call_command(
            "load_dgac_vigencias",
            "--file",
            _csv(tmp_path, [("aircraft", "RPA-3696", future.isoformat())]),
        )

        aircraft.refresh_from_db()
        assert aircraft.insurance_expiry == future
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_FILED

    def test_dry_run_still_writes_nothing(self, tmp_path):
        aircraft = _aircraft()
        future = TODAY + timedelta(days=120)

        call_command(
            "load_dgac_vigencias",
            "--file",
            _csv(tmp_path, [("aircraft", "RPA-3696", future.isoformat())]),
            "--dry-run",
        )

        aircraft.refresh_from_db()
        assert aircraft.insurance_expiry is None
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_MISSING

    def test_operators_are_untouched_by_any_of_this(self, tmp_path):
        """Only the aircraft carries a paired status field; the operator load
        keeps working exactly as before."""
        operator = Operator.objects.create(employee_id="E1", full_name="Piloto")
        future = TODAY + timedelta(days=200)

        call_command(
            "load_dgac_vigencias",
            "--file",
            _csv(tmp_path, [("operator", "Piloto", future.isoformat())]),
        )

        operator.refresh_from_db()
        assert operator.credential_expiry == future
