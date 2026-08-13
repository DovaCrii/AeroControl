"""LV-78 step 3a: the retired board cannot be switched back on by accident.

Freezing a module is not the same as deleting it, and the gap between the two is
where accidents live: the board had no menu entry, no buttons and no charts --
but the alert-rule form still offered to create cards in it, and the deploy
runbook still listed the command that recreates it. Both are documented as
"don't", and in a deploy people follow the procedure, not the footnote.
"""

import pytest
from django.core.management import call_command

from apps.compliance.forms import AlertRuleForm
from apps.compliance.models import AlertRule
from apps.workboard.models import KanbanBoard, KanbanStage


@pytest.mark.django_db
class TestTheFormCannotTurnItOn:
    def test_the_kanban_fields_are_not_offered(self):
        form = AlertRuleForm()

        assert "create_kanban_task" not in form.fields
        assert "target_board" not in form.fields
        assert "target_stage" not in form.fields

    def test_a_posted_value_is_ignored_rather_than_honoured(self):
        """Removing a field from a form is only half a guard if the model still
        accepts it from the payload."""
        board = KanbanBoard.objects.create(name="Frozen")
        stage = KanbanStage.objects.create(board=board, name="Pending")

        form = AlertRuleForm(
            data={
                "name": "Insurance",
                "entity_type": "registry.aircraft",
                "field_to_watch": "insurance_expiry",
                "days_before_expiry": 30,
                "enabled": True,
                "create_kanban_task": True,
                "target_board": str(board.pk),
                "target_stage": str(stage.pk),
            }
        )

        assert form.is_valid(), form.errors
        rule = form.save()
        assert rule.create_kanban_task is False
        assert rule.target_board_id is None

    def test_editing_a_rule_that_has_it_on_does_not_switch_it_off(self):
        """The columns are untouched until the board itself goes. Silently
        rewriting somebody's configuration because they edited the name would be
        the opposite of the careful behaviour this change is after."""
        board = KanbanBoard.objects.create(name="Frozen")
        stage = KanbanStage.objects.create(board=board, name="Pending")
        rule = AlertRule.objects.create(
            name="Legacy",
            entity_type="registry.aircraft",
            field_to_watch="insurance_expiry",
            days_before_expiry=30,
            create_kanban_task=True,
            target_board=board,
            target_stage=stage,
        )

        form = AlertRuleForm(
            instance=rule,
            data={
                "name": "Legacy renamed",
                "entity_type": "registry.aircraft",
                "field_to_watch": "insurance_expiry",
                "days_before_expiry": 30,
                "enabled": True,
            },
        )

        assert form.is_valid(), form.errors
        saved = form.save()
        assert saved.name == "Legacy renamed"
        assert saved.create_kanban_task is True


@pytest.mark.django_db
class TestTheJobSaysSoOutLoud:
    def test_a_rule_still_targeting_the_board_is_named(self, capsys):
        board = KanbanBoard.objects.create(name="Frozen")
        stage = KanbanStage.objects.create(board=board, name="Pending")
        AlertRule.objects.create(
            name="Still filing cards",
            entity_type="registry.aircraft",
            field_to_watch="insurance_expiry",
            days_before_expiry=30,
            create_kanban_task=True,
            target_board=board,
            target_stage=stage,
        )

        call_command("generate_alerts")

        assert "Still filing cards" in capsys.readouterr().out

    def test_an_ordinary_rule_is_not_warned_about(self, capsys):
        AlertRule.objects.create(
            name="Ordinary",
            entity_type="registry.aircraft",
            field_to_watch="insurance_expiry",
            days_before_expiry=30,
        )

        call_command("generate_alerts")

        assert "LV-78" not in capsys.readouterr().out


class TestTheRunbookNoLongerRecreatesIt:
    def test_the_deploy_procedure_does_not_run_init_dgac_board(self):
        """In a deploy people follow the procedure, not the note beside it --
        which is why the command was removed from the list rather than annotated
        with "do not run"."""
        from pathlib import Path

        runbook = (
            Path(__file__).resolve().parents[2] / "docs" / "dev" / "ubuntu-vm-deploy.md"
        )
        text = runbook.read_text(encoding="utf-8")

        assert "manage.py init_dgac_board" not in text
        # It is still explained, so nobody re-adds it wondering why it is absent.
        assert "init_dgac_board" in text
