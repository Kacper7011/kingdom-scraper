"""Control routes: start/stop engine, JSON status endpoint."""

import logging

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from shared.constants import (
    COLLECTION_CONTACTS,
    COLLECTION_OFFERS,
    KEY_ENGINE_STATUS,
    KEY_QUEUE,
    KEY_STAT_ERRORS,
    KEY_STAT_SCRAPED,
    KEY_VISITED,
    SEED_URLS,
    STATUS_RUNNING,
    STATUS_STOPPED,
)

logger = logging.getLogger(__name__)
control_bp = Blueprint("control", __name__)


def _redis():
    return current_app.config["redis"]


@control_bp.route("/control")
def control():
    r = _redis()
    status = r.get(KEY_ENGINE_STATUS) or STATUS_STOPPED
    return render_template("control.html", status=status)


@control_bp.route("/engine/start", methods=["POST"])
def engine_start():
    r = _redis()
    # Remove seed URLs from visited set so they are always re-scraped on start
    if SEED_URLS:
        r.srem(KEY_VISITED, *SEED_URLS)
    queued = 0
    for url in SEED_URLS:
        r.rpush(KEY_QUEUE, url)
        queued += 1
    r.set(KEY_ENGINE_STATUS, STATUS_RUNNING)
    logger.info("Engine start requested — %d seed URLs queued", queued)
    return redirect(url_for("control.control"))


@control_bp.route("/engine/stop", methods=["POST"])
def engine_stop():
    _redis().set(KEY_ENGINE_STATUS, STATUS_STOPPED)
    logger.info("Engine stop requested")
    return redirect(url_for("control.control"))


@control_bp.route("/engine/reset", methods=["POST"])
def engine_reset():
    """Clear queue and visited set so the engine can re-scrape everything."""
    r = _redis()
    r.delete(KEY_QUEUE, KEY_VISITED, KEY_STAT_SCRAPED, KEY_STAT_ERRORS)
    r.set(KEY_ENGINE_STATUS, STATUS_STOPPED)
    logger.info("Engine state reset")
    return redirect(url_for("control.control"))


@control_bp.route("/database/clear", methods=["POST"])
def database_clear():
    """Drop all documents from MongoDB and reset Redis state for a clean re-scrape."""
    db = current_app.config["mongo_db"]
    offers_deleted = db[COLLECTION_OFFERS].delete_many({}).deleted_count
    contacts_deleted = db[COLLECTION_CONTACTS].delete_many({}).deleted_count

    # Reset Redis so the engine can re-scrape everything from scratch
    r = _redis()
    r.delete(KEY_QUEUE, KEY_VISITED, KEY_STAT_SCRAPED, KEY_STAT_ERRORS)
    r.set(KEY_ENGINE_STATUS, STATUS_STOPPED)

    logger.info(
        "Database cleared — offers: %d, contacts: %d; Redis state reset",
        offers_deleted, contacts_deleted,
    )
    return redirect(url_for("control.control"))


@control_bp.route("/engine/status")
def engine_status():
    r = _redis()
    try:
        scraped = int(r.get(KEY_STAT_SCRAPED) or 0)
        errors = int(r.get(KEY_STAT_ERRORS) or 0)
        visited = r.scard(KEY_VISITED)
        queue_len = r.llen(KEY_QUEUE)
        progress_pct = round(scraped / (scraped + queue_len) * 100) if (scraped + queue_len) > 0 else 0
        data = {
            "status": r.get(KEY_ENGINE_STATUS) or STATUS_STOPPED,
            "scraped": scraped,
            "errors": errors,
            "queue_length": queue_len,
            "visited_count": visited,
            "progress_pct": progress_pct,
        }
        return jsonify(data)
    except Exception as exc:
        logger.error("Status endpoint error: %s", exc)
        return jsonify({"status": "error", "detail": str(exc)}), 500


@control_bp.route("/engine/activity")
def engine_activity():
    """Return the 15 most recently scraped offers for the live feed."""
    try:
        col = current_app.config["mongo_db"][COLLECTION_OFFERS]
        docs = list(
            col.find({}, {"_id": 0, "offer_id": 1, "title": 1, "category": 1,
                          "transaction": 1, "price": 1, "address": 1, "scraped_at": 1})
               .sort("scraped_at", -1)
               .limit(15)
        )
        for d in docs:
            if "scraped_at" in d and hasattr(d["scraped_at"], "isoformat"):
                d["scraped_at"] = d["scraped_at"].strftime("%H:%M:%S")
        return jsonify(docs)
    except Exception as exc:
        logger.error("Activity endpoint error: %s", exc)
        return jsonify([]), 500
