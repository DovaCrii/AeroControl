from django.urls import path
from . import views
urlpatterns=[]
for name in ("DocumentType","Document","AlertRule","Alert"):
    n=name.lower(); urlpatterns += [path(f"{n}/",getattr(views,f"{name}List").as_view(),name=f"{n}-list"),path(f"{n}/new/",getattr(views,f"{name}Create").as_view(),name=f"{n}-create")]
