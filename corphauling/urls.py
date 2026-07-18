"""App URLs — Corp Hauling."""

from django.urls import path

from corphauling import views

app_name = "corphauling"

urlpatterns = [
    path("", views.index, name="index"),
    path("mijn/", views.mijn_hauls, name="mijn_hauls"),
    path("mijn/koppel/", views.koppel_contracts, name="koppel_contracts"),
    path("profiel/", views.profiel, name="profiel"),
    path("schip/", views.schip_wisselen, name="schip_wisselen"),
    path("skills/", views.koppel_skills, name="koppel_skills"),
    path("token/", views.grant_access, name="grant_access"),
]
