"""Control routes: start/stop engine, JSON status endpoint."""

import logging

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for

from shared.constants import (
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
    # Push seed URLs that haven't been visited yet
    queued = 0
    for url in SEED_URLS:
        if not r.sismember(KEY_VISITED, url):
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


@control_bp.route("/engine/status")
def engine_status():
    r = _redis()
    try:
        data = {
            "status": r.get(KEY_ENGINE_STATUS) or STATUS_STOPPED,
            "scraped": int(r.get(KEY_STAT_SCRAPED) or 0),
            "errors": int(r.get(KEY_STAT_ERRORS) or 0),
            "queue_length": r.llen(KEY_QUEUE),
            "visited_count": r.scard(KEY_VISITED),
        }
        return jsonify(data)
    except Exception as exc:
        logger.error("Status endpoint error: %s", exc)
        return jsonify({"status": "error", "detail": str(exc)}), 500
