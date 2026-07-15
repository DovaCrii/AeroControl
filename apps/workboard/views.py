from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, CreateView, TemplateView

from apps.core.views import CsvExportMixin, SearchMixin
from apps.registry.models import Operator
from .models import KanbanBoard, KanbanStage, KanbanTask
from .forms import KanbanBoardForm, KanbanStageForm, KanbanTaskForm


class WList(CsvExportMixin, SearchMixin, LoginRequiredMixin, ListView):
    template_name = "generic/list.html"
    context_object_name = "objects"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = self.model._meta.verbose_name_plural.title()
        return c


class WCreate(LoginRequiredMixin, CreateView):
    template_name = "generic/form.html"

    def get_success_url(self):
        return reverse(f"{self.model._meta.model_name}-list")

    def get_context_data(self, **kwargs):
        c = super().get_context_data(**kwargs)
        c["title"] = f"New {self.model._meta.verbose_name.title()}"
        return c


for model, form, name in (
    (KanbanBoard, KanbanBoardForm, "Board"),
    (KanbanStage, KanbanStageForm, "Stage"),
    (KanbanTask, KanbanTaskForm, "Task"),
):
    globals()[f"{name}List"] = type(f"{name}List", (WList,), {"model": model})
    globals()[f"{name}Create"] = type(f"{name}Create", (WCreate,), {"model": model, "form_class": form})


# ─── Kanban Board Views ─────────────────────────────────────


class KanbanBoardView(LoginRequiredMixin, TemplateView):
    """Main kanban board view — all stages and task cards."""

    template_name = "workboard/kanban.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        boards = KanbanBoard.objects.filter(is_active=True)
        board_id = self.request.GET.get("board")
        board = self._get_board(board_id)
        context.update({
            "board": board,
            "boards": boards,
            "operators": self._get_operators(),
            "priorities": KanbanTask.PRIORITIES,
            "drag_enabled": self._filter_values(self.request.GET)[0] is None and not self._filter_values(self.request.GET)[1],
            "stages": self._build_stage_data(board, self.request.GET) if board else [],
            "filter_params": self.request.GET,
        })
        return context

    @staticmethod
    def _filter_values(params):
        operator_id = params.get("operator", "")
        priority = params.get("priority", "")
        try:
            operator = Operator.objects.filter(pk=operator_id, is_active=True).first() if operator_id else None
        except (ValueError, TypeError, ValidationError):
            operator = None
        if priority not in dict(KanbanTask.PRIORITIES):
            priority = ""
        return operator, priority

    @staticmethod
    def _get_board(board_id):
        boards = KanbanBoard.objects.filter(is_active=True)
        if not board_id:
            return boards.first()
        try:
            return boards.filter(pk=board_id).first() or boards.first()
        except (ValueError, TypeError, ValidationError):
            return boards.first()

    def _build_stage_data(self, board, params):
        stages = board.stages.filter(is_active=True).order_by("order")
        operator, priority = self._filter_values(params)
        stage_data = []
        for stage in stages:
            tasks = stage.tasks.filter(is_active=True).order_by("order")
            if operator:
                tasks = tasks.filter(assigned_to=operator)
            if priority:
                tasks = tasks.filter(priority=priority)
            stage_data.append({"stage": stage, "tasks": tasks})
        return stage_data

    def _get_operators(self):
        return Operator.objects.filter(is_active=True).order_by("full_name")


class BoardPartialView(LoginRequiredMixin, View):
    """HTMX fragment — board columns + cards for filter/drag refresh."""

    def get(self, request):
        board_id = request.GET.get("board")
        board = KanbanBoardView._get_board(board_id)

        if not board:
            return HttpResponse('<p class="text-muted text-center py-5">No board configured.</p>')

        stage_data = KanbanBoardView()._build_stage_data(board, request.GET)
        return render(request, "workboard/_board.html", {
            "board": board,
            "stages": stage_data,
            "drag_enabled": KanbanBoardView._filter_values(request.GET)[0] is None and not KanbanBoardView._filter_values(request.GET)[1],
            "filter_params": request.GET,
        })


class MoveTaskView(LoginRequiredMixin, View):
    """Drag-and-drop: move task between stages and re-order siblings."""

    def post(self, request, pk):
        task = get_object_or_404(
            KanbanTask, pk=pk, is_active=True, board__is_active=True, stage__is_active=True,
        )
        old_stage_id = task.stage_id

        stage_id = request.POST.get("stage_id")
        raw_order = request.POST.get("new_order", "0")

        try:
            new_order = max(int(raw_order), 0)
            new_stage = KanbanStage.objects.filter(
                pk=stage_id,
                board_id=task.board_id,
                is_active=True,
            ).first()
        except (ValueError, TypeError, ValidationError):
            return HttpResponse(status=400)
        if new_stage is None or task.stage.board_id != task.board_id:
            return HttpResponse(status=400)

        with transaction.atomic():
            old_stage = KanbanStage.objects.get(pk=old_stage_id)
            self._remove_from_stage(task, old_stage)
            task.stage = new_stage
            task.save(update_fields=["stage", "updated_at"])
            self._insert_into_stage(task, new_stage, new_order)

        return HttpResponse(status=204, headers={"HX-Trigger": "board-refresh"})

    @staticmethod
    def _remove_from_stage(task, stage):
        siblings = list(stage.tasks.filter(is_active=True).exclude(pk=task.pk).order_by("order", "created_at"))
        for index, sibling in enumerate(siblings):
            if sibling.order != index:
                KanbanTask.objects.filter(pk=sibling.pk).update(order=index)

    @staticmethod
    def _insert_into_stage(task, stage, order):
        siblings = list(stage.tasks.filter(is_active=True).exclude(pk=task.pk).order_by("order", "created_at"))
        siblings.insert(min(order, len(siblings)), task)
        for index, sibling in enumerate(siblings):
            if sibling.pk == task.pk:
                if task.order != index:
                    KanbanTask.objects.filter(pk=task.pk).update(order=index)
            elif sibling.order != index:
                KanbanTask.objects.filter(pk=sibling.pk).update(order=index)


class QuickTaskCreate(LoginRequiredMixin, View):
    """Quick-add a task from the column footer, returns refreshed column."""

    def get(self, request):
        """Return the quick-add form fragment for a given stage."""
        stage_id = request.GET.get("stage_id")
        if not stage_id:
            return HttpResponse(status=400)
        try:
            stage = KanbanStage.objects.filter(
                pk=stage_id, is_active=True, board__is_active=True,
            ).first()
        except (ValueError, TypeError, ValidationError):
            stage = None
        if stage is None:
            return HttpResponse(status=400)
        operators = KanbanBoardView()._get_operators()
        return render(request, "workboard/_quick_form.html", {
            "stage": stage,
            "operators": operators,
            "filter_params": request.GET,
        })

    def post(self, request):
        stage_id = request.POST.get("stage_id")
        title = request.POST.get("title", "").strip()
        assigned_to = request.POST.get("assigned_to") or None
        priority = request.POST.get("priority", "medium")

        if not title or not stage_id or priority not in dict(KanbanTask.PRIORITIES):
            return HttpResponse(status=400)

        try:
            stage = KanbanStage.objects.filter(
                pk=stage_id, is_active=True, board__is_active=True,
            ).first()
        except (ValueError, TypeError, ValidationError):
            stage = None
        if stage is None:
            return HttpResponse(status=400)
        if assigned_to:
            try:
                operator = Operator.objects.filter(pk=assigned_to, is_active=True).first()
            except (ValueError, TypeError, ValidationError):
                return HttpResponse(status=400)
            if operator is None:
                return HttpResponse(status=400)
        max_order = KanbanTask.objects.filter(stage=stage, is_active=True).count()

        KanbanTask.objects.create(
            board=stage.board,
            stage=stage,
            title=title,
            priority=priority,
            assigned_to_id=assigned_to,
            created_by=request.user.get_username(),
            order=max_order,
        )

        filter_params = request.POST.copy()
        filter_priority = filter_params.get("filter_priority", "")
        if filter_priority:
            filter_params["priority"] = filter_priority
        else:
            filter_params.pop("priority", None)
        operator, valid_priority = KanbanBoardView._filter_values(filter_params)
        tasks = stage.tasks.filter(is_active=True).order_by("order")
        if operator:
            tasks = tasks.filter(assigned_to=operator)
        if valid_priority:
            tasks = tasks.filter(priority=valid_priority)
        return render(request, "workboard/_column.html", {
            "stage": stage,
            "tasks": tasks,
            "drag_enabled": operator is None and not valid_priority,
            "filter_params": filter_params,
        })


class BoardSelector(LoginRequiredMixin, View):
    """Board switcher dropdown fragment."""

    def get(self, request):
        boards = KanbanBoard.objects.filter(is_active=True)
        current = request.GET.get("board")
        return render(request, "workboard/_board_selector.html", {
            "boards": boards, "current": current,
        })


# Backwards-compatible name used by earlier workboard integrations.
BoardFilterPartial = BoardPartialView

