"""Single worker process: asyncio event loop with a coroutine pool."""

import asyncio
import logging
import os

from shared.constants import (
    COROUTINES_PER_WORKER,
    KEY_STAT_ERRORS,
    KEY_STAT_SCRAPED,
    STATUS_RUNNING,
    STATUS_STOPPED,
    TARGET_URL,
)
from crawler import CrawlerError, build_session, fetch_page, get_next_page_url
from db_writer import DBError, _get_client, ensure_indexes, save_contact, save_offer
from parser import ParserError, parse_contact, parse_listing_urls, parse_offer
from queue_manager import QueueError, QueueManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(processName)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

# How many consecutive empty pops before the coroutine shuts down
_IDLE_LIMIT = 6  # 6 × 5 s timeout = 30 s idle → exit


async def _pop_url_async(queue: QueueManager, timeout: int = 5) -> str | None:
    """Run the blocking Redis BLPOP in a thread so the event loop stays free."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, queue.pop_url, timeout)


async def _process_url(url: str, session, queue: QueueManager, db_client) -> None:
    """Fetch one URL, parse it, persist results, and enqueue discovered links."""
    try:
        html = await fetch_page(session, url)
    except CrawlerError as exc:
        logger.error("Crawler error [%s]: %s", url, exc)
        queue.increment_stat(KEY_STAT_ERRORS)
        return

    # Offer detail page
    if "/oferta/" in url:
        offer = parse_offer(html, url)
        if offer:
            try:
                save_offer(db_client, offer)
                queue.increment_stat(KEY_STAT_SCRAPED)
                logger.info("Saved offer: %s", offer.offer_id)
            except DBError as exc:
                logger.error("DB error saving offer %s: %s", url, exc)
                queue.increment_stat(KEY_STAT_ERRORS)

        contact = parse_contact(html)
        if contact and contact.email:
            try:
                save_contact(db_client, contact)
            except DBError as exc:
                logger.error("DB error saving contact: %s", exc)

    # Listing / category page — harvest offer links and pagination
    else:
        new_links = parse_listing_urls(html, TARGET_URL)
        next_page = get_next_page_url(html, url)
        if next_page:
            new_links.append(next_page)
        added = queue.push_many(new_links)
        logger.info("Listing %s — %d new links queued", url, added)

    queue.mark_visited(url)


async def _worker_loop(worker_id: int, queue: QueueManager, db_client) -> None:
    """Coroutine: pop URLs and process them until the queue is idle too long."""
    idle_ticks = 0
    async with build_session() as session:
        while True:
            if queue.get_engine_status() == STATUS_STOPPED:
                logger.info("Worker-%d received stop signal", worker_id)
                break

            try:
                url = await _pop_url_async(queue, timeout=5)
            except QueueError as exc:
                logger.error("Queue error: %s", exc)
                await asyncio.sleep(5)
                continue

            if url is None:
                idle_ticks += 1
                if idle_ticks >= _IDLE_LIMIT:
                    logger.info("Worker-%d: queue empty for 30 s, exiting", worker_id)
                    break
                continue

            idle_ticks = 0
            if queue.is_visited(url):
                continue

            await _process_url(url, session, queue, db_client)


def run_worker(worker_id: int) -> None:
    """Entry point for a single worker process spawned by engine/main.py."""
    logger.info("Worker-%d starting (pid=%d)", worker_id, os.getpid())

    queue = QueueManager()
    db_client = _get_client()
    ensure_indexes(db_client)
    queue.set_engine_status(STATUS_RUNNING)

    n = int(os.getenv("COROUTINES_PER_WORKER", str(COROUTINES_PER_WORKER)))

    async def _run_all() -> None:
        tasks = [_worker_loop(worker_id, queue, db_client) for _ in range(n)]
        await asyncio.gather(*tasks)

    try:
        asyncio.run(_run_all())
    except KeyboardInterrupt:
        logger.info("Worker-%d interrupted", worker_id)
    finally:
        # Only update status on explicit stop signal, not on idle exit —
        # main.py sets the final stopped status after all workers finish.
        db_client.close()
        logger.info("Worker-%d stopped", worker_id)
