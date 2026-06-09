"""Dashboard routes: paginated offer list and statistics."""

import logging

from flask import Blueprint, current_app, render_template, request

from shared.constants import (
    KEY_ENGINE_STATUS,
    KEY_STAT_ERRORS,
    KEY_STAT_SCRAPED,
    KEY_VISITED,
    KEY_QUEUE,
    STATUS_STOPPED,
    COLLECTION_OFFERS,
)

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)

PAGE_SIZE = 12


def _get_offers(page: int) -> tuple[list[dict], int]:
    col = current_app.config["mongo_db"][COLLECTION_OFFERS]
    skip = (page - 1) * PAGE_SIZE
    total = col.count_documents({})
    offers = list(
        col.find({}, {"_id": 0})
        .sort("scraped_at", -1)
        .skip(skip)
        .limit(PAGE_SIZE)
    )
    return offers, total


def _get_redis_stats() -> dict:
    r = current_app.config["redis"]
    try:
        return {
            "scraped": int(r.get(KEY_STAT_SCRAPED) or 0),
            "errors": int(r.get(KEY_STAT_ERRORS) or 0),
            "queue_length": r.llen(KEY_QUEUE),
            "visited_count": r.scard(KEY_VISITED),
            "status": r.get(KEY_ENGINE_STATUS) or STATUS_STOPPED,
        }
    except Exception as exc:
        logger.error("Redis stats error: %s", exc)
        return {"scraped": 0, "errors": 0, "queue_length": 0, "visited_count": 0, "status": "error"}


@dashboard_bp.route("/")
def index():
    page = max(1, request.args.get("page", 1, type=int))
    offers, total = _get_offers(page)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    stats = _get_redis_stats()
    return render_template(
        "dashboard.html",
        offers=offers,
        page=page,
        total_pages=total_pages,
        total=total,
        stats=stats,
    )


@dashboard_bp.route("/offers/<offer_id>")
def offer_detail(offer_id: str):
    col = current_app.config["mongo_db"][COLLECTION_OFFERS]
    offer = col.find_one({"offer_id": offer_id}, {"_id": 0})
    if not offer:
        return render_template("404.html"), 404
    return render_template("offer_detail.html", offer=offer)
