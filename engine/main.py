"""Engine entry point: long-running daemon that responds to Redis start/stop signals."""

import logging
import multiprocessing
import os
import signal
import sys
import time

from shared.constants import SEED_URLS, STATUS_RUNNING, STATUS_STOPPED, TARGET_URL, WORKER_COUNT
from queue_manager import QueueError, QueueManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(processName)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

_processes: list[multiprocessing.Process] = []
_stop_requested = False


def _shutdown(signum, frame) -> None:
    """Handle SIGTERM / SIGINT — stop workers and exit the daemon."""
    global _stop_requested
    _stop_requested = True
    logger.info("Shutdown signal received — terminating workers")
    try:
        QueueManager().set_engine_status(STATUS_STOPPED)
    except QueueError:
        pass
    for proc in _processes:
        if proc.is_alive():
            proc.terminate()
    for proc in _processes:
        proc.join(timeout=10)
    logger.info("Engine daemon stopped")
    sys.exit(0)


def _seed_queue(queue: QueueManager) -> None:
    """Push seed URLs that have not been visited yet."""
    added = queue.push_many(SEED_URLS)
    logger.info("Seeded queue with %d URL(s) (target: %s)", added, TARGET_URL)


def _spawn_workers(n: int) -> None:
    from worker import run_worker

    _processes.clear()
    for i in range(n):
        proc = multiprocessing.Process(
            target=run_worker,
            args=(i,),
            name=f"Worker-{i}",
            daemon=False,
        )
        proc.start()
        _processes.append(proc)
        logger.info("Spawned %s (pid=%d)", proc.name, proc.pid)


def _wait_for_workers() -> None:
    for proc in _processes:
        proc.join()


def main() -> None:
    n = int(os.getenv("WORKER_COUNT", str(WORKER_COUNT)))

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        queue = QueueManager()
    except QueueError as exc:
        logger.error("Cannot connect to Redis: %s", exc)
        sys.exit(1)

    logger.info("Engine daemon ready — waiting for start signal (workers: %d)", n)

    while not _stop_requested:
        try:
            status = queue.get_engine_status()
        except QueueError as exc:
            logger.error("Redis error while polling status: %s", exc)
            time.sleep(5)
            continue

        if status == STATUS_RUNNING:
            logger.info("Start signal received — seeding queue and spawning workers")
            _seed_queue(queue)
            _spawn_workers(n)
            _wait_for_workers()
            _processes.clear()
            # Only set stopped if UI hasn't already done it
            try:
                if queue.get_engine_status() == STATUS_RUNNING:
                    queue.set_engine_status(STATUS_STOPPED)
            except QueueError:
                pass
            logger.info("All workers finished — engine idle, waiting for next start signal")
        else:
            time.sleep(3)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
