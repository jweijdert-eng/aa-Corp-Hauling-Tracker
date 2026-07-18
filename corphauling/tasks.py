"""Celery-taken — Corp Hauling."""

import logging

from celery import shared_task

from .esi import open_couriers
from .models import Config
from .profit import enrich

logger = logging.getLogger(__name__)


@shared_task
def refresh_contracts():
    """Haal de contracten op en warm meteen de locatie- en route-cache.

    Zo is de pagina voor de gebruiker altijd snel: de dure route-lookups
    zijn dan al gedaan door de worker.
    """
    cfg = Config.load()
    contracts, corp_id = open_couriers(cfg.corp_id, ttl=cfg.cache_minutes * 60, force=True)
    if not contracts:
        logger.info("Corp Hauling: geen open koeriers-contracten (corp %s)", corp_id)
        return 0

    for contract in contracts:
        try:
            enrich(contract, cfg.isk_per_jump, cfg.route_voorkeur, cfg)  # vult locatie-, systeem- en route-cache
        except Exception:  # noqa: BLE001 — één rot contract mag de taak niet stoppen
            logger.warning("Contract %s kon niet verrijkt worden",
                           contract.get("contract_id"), exc_info=True)

    logger.info("Corp Hauling: %s open koeriers-contracten ververst", len(contracts))
    return len(contracts)
