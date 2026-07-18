"""Hook into Alliance Auth — Corp Hauling verdiensten-tracker."""

from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from corphauling import urls


class CorpHaulingMenuItem(MenuItemHook):
    """Menu-item voor wie de haul-verdiensten mag bekijken."""

    def __init__(self):
        MenuItemHook.__init__(
            self,
            _("Corp Hauling"),
            "fas fa-truck fa-fw",
            "corphauling:index",
            navactive=["corphauling:"],
        )

    def render(self, request):
        if request.user.has_perm("corphauling.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return CorpHaulingMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "corphauling", r"^corp-hauling/")
