"""Application-wide constants loaded from environment variables."""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Target ---
TARGET_URL: str = os.getenv("TARGET_URL", "https://www.kingdomelblag.pl")

# Seed URLs cover all main listing categories
SEED_URLS: list[str] = [
    f"{TARGET_URL}/oferty/mieszkania-sprzedaz",
    f"{TARGET_URL}/oferty/domy-sprzedaz",
    f"{TARGET_URL}/oferty/dzialki-sprzedaz",
    f"{TARGET_URL}/oferty/lokale-sprzedaz",
    f"{TARGET_URL}/oferty/mieszkania-wynajem",
    f"{TARGET_URL}/oferty/domy-wynajem",
    f"{TARGET_URL}/oferty/lokale-wynajem",
    f"{TARGET_URL}/oferty/dzialki-dzierzawa",
    f"{TARGET_URL}/kontakt",
]

# --- MongoDB ---
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB: str = os.getenv("MONGO_DB", "kingdom_scraper")

COLLECTION_OFFERS: str = "offers"
COLLECTION_CONTACTS: str = "contacts"

# --- Redis keys ---
REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

KEY_QUEUE: str = "queue:urls"
KEY_VISITED: str = "set:visited"
KEY_STAT_SCRAPED: str = "stats:scraped"
KEY_STAT_ERRORS: str = "stats:errors"
KEY_ENGINE_STATUS: str = "engine:status"

STATUS_RUNNING: str = "running"
STATUS_STOPPED: str = "stopped"

# --- Engine tuning ---
WORKER_COUNT: int = int(os.getenv("WORKER_COUNT", str(os.cpu_count() or 4)))
COROUTINES_PER_WORKER: int = int(os.getenv("COROUTINES_PER_WORKER", "8"))
REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "1.0"))

# --- HTTP ---
USER_AGENT: str = (
    "Mozilla/5.0 (compatible; KingdomScraper/1.0; +https://github.com/Kacper7011/kingdom-scraper)"
)
REQUEST_TIMEOUT: int = 30
