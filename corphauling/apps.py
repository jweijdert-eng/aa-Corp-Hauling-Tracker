"""App Configuration"""

from django.apps import AppConfig

from corphauling import __version__


class CorpHaulingConfig(AppConfig):
    name = "corphauling"
    label = "corphauling"
    verbose_name = f"Corp Hauling Tracker v{__version__}"
