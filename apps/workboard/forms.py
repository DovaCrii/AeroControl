from django import forms
from .models import KanbanBoard,KanbanStage,KanbanTask
for model in (KanbanBoard,KanbanStage,KanbanTask): globals()[f"{model.__name__}Form"] = type(f"{model.__name__}Form",(forms.ModelForm,),{"Meta":type("Meta",(),{"model":model,"fields":"__all__"})})
