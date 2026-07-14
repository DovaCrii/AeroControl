from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.views.generic import ListView, CreateView
from apps.core.views import SearchMixin
from .models import KanbanBoard, KanbanStage, KanbanTask
from .forms import KanbanBoardForm, KanbanStageForm, KanbanTaskForm


class WList(SearchMixin, LoginRequiredMixin, ListView):
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
