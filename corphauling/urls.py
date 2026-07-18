"""App URLs — Corp Hauling."""

from django.urls import path

from corphauling import views

app_name = "corphauling"

urlpatterns = [
    path("", views.index, name="index"),
    path("profiel/", views.profiel, name="profiel"),
    path("schip/", views.schip_wisselen, name="schip_wisselen"),
    path("token/", views.grant_access, name="grant_access"),
]
