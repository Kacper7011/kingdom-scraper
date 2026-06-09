"""Engine entry point: seeds Redis queue and spawns worker processes."""

import logging
import multiprocessing
import os
import signal
import sys

from shared.constants import SEED_URLS, STATUS_STOPPED, TARGET_URL, WORKER_COUNT
from queue_manager import QueueError, QueueManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(processName)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

_processes: list[multiprocessing.Process] = []


def _shutdown(signum, frame) -> None:
    """Gracefully stop all worker processes on SIGTERM / SIGINT."""
    logger.info("Shutdown signal received — stopping %d worker(s)", len(_processes))
    try:
        qm = QueueManager()
        qm.set_engine_status(STATUS_STOPPED)
    except QueueError:
        pass

    for proc in _processes:
        if proc.is_alive():
            proc.terminate()

    for proc in _processes:
        proc.join(timeout=10)

    logger.info("All workers stopped")
    sys.exit(0)


def _seed_queue(queue: QueueManager) -> None:
    added = queue.push_many(SEED_URLS)
    logger.info("Seeded queue with %d URL(s) (target: %s)", added, TARGET_URL)


def _spawn_workers(n: int) -> None:
    from worker import run_worker

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


def main() -> None:
    n = int(os.getenv("WORKER_COUNT", str(WORKER_COUNT)))
    logger.info("Engine starting — workers: %d, target: %s", n, TARGET_URL)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        queue = QueueManager()
    except QueueError as exc:
        logger.error("Cannot connect to Redis: %s", exc)
        sys.exit(1)

    _seed_queue(queue)
    _spawn_workers(n)

    logger.info("All %d worker(s) running — waiting for completion", n)
    for proc in _processes:
        proc.join()

    try:
        QueueManager().set_engine_status(STATUS_STOPPED)
    except QueueError:
        pass

    logger.info("Engine finished")


if __name__ == "__main__":
    # Required on Windows to avoid recursive process spawning
    multiprocessing.freeze_support()
    main()
