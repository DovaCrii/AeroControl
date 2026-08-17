"""LV-81: the JAC insurance filing, its four states and its trace.

What the user asked for, in his words: *"en trámite o faltante para actualizar"*,
*"se subió a SIGO y se espera la aprobación de la JAC"*, and *"la misma barra de
estado y trazabilidad que usamos en los permisos"*. The four states are not a
guess: SIGO shows each aircraft as "Pendiente" or "Autorizada", and the
certificate the user provided (policy 95131 / certificate 136) belongs to the one
aircraft SIGO still lists as pending.

The tests that pin the *removed* half of R5.7's rule live here rather than being
deleted from that file, so the reason the premise changed stays recorded next to
the new behaviour.
"""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.testing import login_as
from apps.registry.models import Aircraft, InsuranceHistory

TODAY = timezone.localdate()


def _aircraft(**kwargs):
    return Aircraft.objects.create(
        registration=kwargs.pop("registration", "CC-AAA"),
        type="RPA",
        model="M3",
        manufacturer="DJI",
        **kwargs,
    )


@pytest.mark.django_db
class TestTheFourStates:
    def test_a_new_aircraft_has_no_insurance_rather_than_an_active_one(self):
        """R5.7 defaulted this to "active", which is how three production
        aircraft ended up reading "Vigente" with no date beside them."""
        assert _aircraft().insurance_status == Aircraft.INSURANCE_STATUS_MISSING

    def test_filed_is_distinguishable_from_missing(self):
        """The whole point: "insurance bought and waiting for the JAC" and "no
        insurance at all" used to be the same value."""
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_FILED)
        aircraft.full_clean()

        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_FILED
        assert (
            aircraft.get_insurance_status_display()
            != _aircraft(registration="CC-BBB").get_insurance_status_display()
        )


@pytest.mark.django_db
class TestContradictionsAreNormalized:
    def test_active_with_no_date_reads_as_missing(self):
        """The DGAC does not authorize a policy with no validity period, so this
        pair is not a state that exists -- it is nothing on file."""
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE)
        aircraft.full_clean()

        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_MISSING

    def test_missing_while_a_policy_is_still_valid_reads_as_active(self):
        aircraft = _aircraft(
            insurance_status=Aircraft.INSURANCE_STATUS_MISSING,
            insurance_expiry=TODAY + timedelta(days=200),
        )
        aircraft.full_clean()

        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE

    def test_missing_with_a_lapsed_policy_stays_missing(self):
        """An expiry already in the past is exactly what "missing or to be
        renewed" should say, so it must not be normalized away."""
        aircraft = _aircraft(
            insurance_status=Aircraft.INSURANCE_STATUS_MISSING,
            insurance_expiry=TODAY - timedelta(days=1),
        )
        aircraft.full_clean()

        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_MISSING

    @pytest.mark.parametrize(
        "status", [Aircraft.INSURANCE_STATUS_PENDING, Aircraft.INSURANCE_STATUS_FILED]
    )
    def test_a_renewal_in_progress_survives_a_valid_date(self, status):
        """**This is the half of R5.7's rule that LV-81 removed.** It used to
        force "active" whenever an expiry existed, which made the user's
        "faltante para actualizar" impossible to record: while the current policy
        still has its end date on file, the next one is being arranged."""
        aircraft = _aircraft(
            insurance_status=status, insurance_expiry=TODAY + timedelta(days=20)
        )
        aircraft.full_clean()

        assert aircraft.insurance_status == status

    def test_a_blank_status_follows_the_date_on_file(self):
        with_date = _aircraft(
            insurance_status="", insurance_expiry=TODAY + timedelta(days=10)
        )
        with_date.full_clean()
        without = _aircraft(registration="CC-BBB", insurance_status="")
        without.full_clean()

        assert with_date.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE
        assert without.insurance_status == Aircraft.INSURANCE_STATUS_MISSING


@pytest.mark.django_db
class TestStepper:
    def test_missing_has_not_started_the_flow(self):
        """ "Missing" is not step one: rendering it as reached would claim a
        filing that nobody opened."""
        steps = _aircraft().insurance_steps()

        assert [step["state"] for step in steps] == ["pending"] * 3
        assert [step["code"] for step in steps] == Aircraft.INSURANCE_FLOW

    def test_the_current_step_is_the_one_it_stands_on(self):
        steps = _aircraft(
            insurance_status=Aircraft.INSURANCE_STATUS_FILED
        ).insurance_steps()

        assert [step["state"] for step in steps] == ["done", "current", "pending"]

    def test_authorized_completes_the_flow(self):
        steps = _aircraft(
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=100),
        ).insurance_steps()

        assert [step["state"] for step in steps] == ["done", "done", "current"]

    def test_the_airframe_status_is_untouched_by_the_insurance_flow(self):
        """An aircraft's own `status` is its condition, not a progression --
        which is why this is a separate stepper and not StatusFlowMixin."""
        aircraft = _aircraft(
            status="maintenance", insurance_status=Aircraft.INSURANCE_STATUS_FILED
        )

        assert aircraft.status == "maintenance"
        assert len(aircraft.insurance_steps()) == 3


@pytest.mark.django_db
class TestTrace:
    def test_a_change_is_recorded_with_who_made_it(self):
        aircraft = _aircraft()
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_PENDING
        aircraft._changed_by = "cmunoz"
        aircraft.save()

        entry = InsuranceHistory.objects.get(aircraft=aircraft)
        assert entry.previous_status == Aircraft.INSURANCE_STATUS_MISSING
        assert entry.new_status == Aircraft.INSURANCE_STATUS_PENDING
        assert entry.changed_by == "cmunoz"

    def test_saving_without_changing_the_status_records_nothing(self):
        aircraft = _aircraft()
        aircraft.model = "M300"
        aircraft.save()

        assert not InsuranceHistory.objects.exists()

    def test_the_airframe_status_changing_does_not_write_an_insurance_row(self):
        """Both flows now go through the same signal; the wrong one firing here
        would fill the insurance trace with maintenance moves."""
        aircraft = _aircraft()
        aircraft.status = "maintenance"
        aircraft.save()

        assert not InsuranceHistory.objects.exists()

    def test_the_display_labels_are_translatable(self):
        """R2.5's defect: without `choices` on the history fields Django never
        generates get_new_status_display, and the table falls through to the raw
        code inside a Spanish page."""
        aircraft = _aircraft()
        aircraft.insurance_status = Aircraft.INSURANCE_STATUS_FILED
        aircraft.save()

        entry = InsuranceHistory.objects.get(aircraft=aircraft)
        assert entry.get_new_status_display() != entry.new_status

    def test_rows_are_ordered_by_their_own_sequence(self):
        """`created_at` ties: timezone.now() can return the identical value
        across rapid successive saves."""
        aircraft = _aircraft()
        for status in (
            Aircraft.INSURANCE_STATUS_PENDING,
            Aircraft.INSURANCE_STATUS_FILED,
        ):
            aircraft.insurance_status = status
            aircraft.save()

        assert [entry.new_status for entry in aircraft.insurance_history.all()] == [
            Aircraft.INSURANCE_STATUS_FILED,
            Aircraft.INSURANCE_STATUS_PENDING,
        ]


@pytest.mark.django_db
class TestTransitions:
    def _url(self, aircraft, step):
        return reverse(f"aircraft-insurance-{step}", args=[aircraft.pk])

    def test_the_filing_advances_one_step_at_a_time(self):
        # The date is on file from the start here: the last step requires it
        # (see test_authorizing_requires_the_validity_date).
        aircraft = _aircraft(insurance_expiry=TODAY + timedelta(days=365))
        client = login_as("change_aircraft", "view_aircraft")

        client.post(self._url(aircraft, "pending"))
        aircraft.refresh_from_db()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_PENDING

        client.post(self._url(aircraft, "filed"))
        aircraft.refresh_from_db()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_FILED

        client.post(self._url(aircraft, "active"))
        aircraft.refresh_from_db()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_ACTIVE

    def test_authorizing_requires_the_validity_date(self):
        """Found on the screen: the fiche read "Póliza vigente" and "Sin
        vigencia de póliza en ficha" at the same time, because a transition
        writes only the status and never runs `clean()`. Same guard as the
        permit's signed-PDF requirement -- the status must not outrun the
        paperwork."""
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_FILED)

        response = login_as("change_aircraft", "view_aircraft").post(
            self._url(aircraft, "active"), follow=True
        )

        aircraft.refresh_from_db()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_FILED
        assert any("vigencia" in str(m).lower() for m in response.context["messages"])

    def test_skipping_a_step_is_refused(self):
        aircraft = _aircraft()

        login_as("change_aircraft", "view_aircraft").post(self._url(aircraft, "active"))

        aircraft.refresh_from_db()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_MISSING

    def test_a_renewal_starts_the_cycle_again_from_active(self):
        aircraft = _aircraft(
            insurance_status=Aircraft.INSURANCE_STATUS_ACTIVE,
            insurance_expiry=TODAY + timedelta(days=15),
        )

        login_as("change_aircraft", "view_aircraft").post(
            self._url(aircraft, "pending")
        )

        aircraft.refresh_from_db()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_PENDING
        # And the date it still carries is untouched: the old policy is valid
        # until the new one is authorized.
        assert aircraft.insurance_expiry == TODAY + timedelta(days=15)

    def test_it_requires_change_aircraft(self):
        aircraft = _aircraft()

        response = login_as("view_aircraft").post(self._url(aircraft, "pending"))

        assert response.status_code == 403
        aircraft.refresh_from_db()
        assert aircraft.insurance_status == Aircraft.INSURANCE_STATUS_MISSING

    def test_a_transition_never_touches_the_airframe_status(self):
        """`status_field` is what keeps these apart -- pointing the transition
        at `status` would ground an aircraft as a side effect of its policy
        being authorized."""
        aircraft = _aircraft(status="active")

        login_as("change_aircraft", "view_aircraft").post(
            self._url(aircraft, "pending")
        )

        aircraft.refresh_from_db()
        assert aircraft.status == "active"

    def test_the_transition_is_attributed_to_the_user_who_made_it(self):
        aircraft = _aircraft()

        login_as("change_aircraft", "view_aircraft").post(
            self._url(aircraft, "pending")
        )

        entry = InsuranceHistory.objects.get(aircraft=aircraft)
        assert entry.changed_by == "u-change_aircraft-view_aircraft"
        assert entry.changed_by_user is not None


@pytest.mark.django_db
class TestOnThePage:
    def test_the_fiche_shows_the_stepper_and_the_next_action(self):
        aircraft = _aircraft(insurance_status=Aircraft.INSURANCE_STATUS_FILED)

        response = login_as("view_aircraft", "change_aircraft").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )

        assert response.status_code == 200
        assert [step["state"] for step in response.context["insurance_steps"]] == [
            "done",
            "current",
            "pending",
        ]
        # Asserted on the route, not the label: the label is translated, and
        # what matters is that the only offered action is the next step.
        assert [url for _label, url in response.context["insurance_actions"]] == [
            reverse("aircraft-insurance-active", args=[aircraft.pk])
        ]

    def test_without_change_aircraft_there_are_no_buttons(self):
        aircraft = _aircraft()

        response = login_as("view_aircraft").get(
            reverse("aircraft-detail", args=[aircraft.pk])
        )

        assert response.context["insurance_actions"] == []

    def test_the_lapsed_policy_is_flagged_on_the_fiche(self):
        aircraft = _aircraft(
            insurance_status=Aircraft.INSURANCE_STATUS_MISSING,
            insurance_expiry=TODAY - timedelta(days=3),
        )

        content = (
            login_as("view_aircraft")
            .get(reverse("aircraft-detail", args=[aircraft.pk]))
            .content.decode()
        )

        assert "Vencida" in content or "Lapsed" in content
