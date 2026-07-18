"""Hook into Alliance Auth — Corp Hauling."""

import logging

from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

from corphauling import urls

logger = logging.getLogger(__name__)


class CorpHaulingMenuItem(MenuItemHook):
    """Menu-item met een badge = aantal open koeriers-contracten."""

    def __init__(self):
        MenuItemHook.__init__(
            self,
            _("Corp Hauling"),
            "fas fa-truck fa-fw",
            "corphauling:index",
            navactive=["corphauling:"],
        )

    def render(self, request):
        if not request.user.has_perm("corphauling.basic_access"):
            return ""
        # Badge alleen uit de cache — nooit een ESI-call tijdens het menu renderen.
        try:
            from django.core.cache import cache

            from .models import Config

            cfg = Config.load()
            rows = cache.get(f"cc_contracts_{cfg.corp_id}")
            if rows is not None:
                self.count = sum(
                    1 for c in rows
                    if c.get("type") == "courier" and c.get("status") == "outstanding"
                ) or None
        except Exception:  # noqa: BLE001 — een badge mag het menu nooit slopen
            logger.debug("Badge voor Corp Hauling kon niet bepaald worden", exc_info=True)
        return MenuItemHook.render(self, request)


@hooks.register("menu_item_hook")
def register_menu():
    return CorpHaulingMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(urls, "corphauling", r"^corp-hauling/")
