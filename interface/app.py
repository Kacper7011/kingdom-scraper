"""Flask application factory for kingdom-scraper interface."""

import logging
import os

import redis
from flask import Flask
from pymongo import MongoClient

from shared.constants import MONGO_DB, MONGO_URI, REDIS_HOST, REDIS_PORT

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(processName)s] %(levelname)s — %(message)s",
)


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.getenv("SECRET_KEY", "change_me")

    app.config["mongo_client"] = MongoClient(MONGO_URI)
    app.config["mongo_db"] = app.config["mongo_client"][MONGO_DB]
    app.config["redis"] = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    from routes.dashboard import dashboard_bp
    from routes.control import control_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(control_bp)

    return app


if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    create_app().run(host="0.0.0.0", port=port, debug=debug)
