"""App URLs — Corp Hauling verdiensten-tracker."""

from django.urls import path

from corphauling import views

app_name = "corphauling"

urlpatterns = [
    path("", views.index, name="index"),
    path("koppel/", views.koppel_contracts, name="koppel_contracts"),
]
