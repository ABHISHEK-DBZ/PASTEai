from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import redis
import rq
from sqlalchemy import select

from app.config import settings
from app.db import session_context
from app.events import publish
from app.models import Product, ProductStatus
from app.pipeline import process_product

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("paste-worker")


redis_conn = redis.from_url(settings.redis_url)
queue = rq.Queue("processing", connection=redis_conn, default_timeout=3600)


def _publish_status(product: Product) -> None:
    publish(
        "product:status",
        {
            "product_id": str(product.id),
            "status": product.status.value,
            "part_number": product.part_number,
            "source_filename": product.source_filename,
        },
    )


def process_job(product_id: str, file_path: str):
    """RQ job function - runs in worker process."""
    asyncio.run(_process_job_async(product_id, file_path))


async def _process_job_async(product_id: str, file_path: str):
    logger.info(f"Processing product {product_id} from {file_path}")

    async with session_context() as session:
        product = await session.get(Product, product_id)
        if not product:
            logger.warning(f"Product {product_id} not found, skipping")
            return
        product.status = ProductStatus.PROCESSING
        await session.flush()
        await session.commit()
        _publish_status(product)

        try:
            await process_product(product_id, Path(file_path), session)
            product = await session.get(Product, product_id)
            if product:
                await session.commit()
                _publish_status(product)
            logger.info(f"Completed product {product_id}")
        except Exception as e:
            logger.exception(f"Failed to process product {product_id}: {e}")
            product = await session.get(Product, product_id)
            if product:
                product.status = ProductStatus.FAILED
                await session.commit()
                _publish_status(product)


def main():
    logger.info("Starting PASTE worker...")

    # Graceful shutdown
    def shutdown(signum, frame):
        logger.info("Shutdown signal received")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # RQ's default Worker forks to isolate each job; Windows has no os.fork, so
    # use SimpleWorker there (runs jobs in-process, sequentially - fine for dev).
    # Its default death penalty is UnixSignalDeathPenalty (needs SIGALRM, also
    # Unix-only), so swap in the threading-based TimerDeathPenalty.
    if os.name == "nt":
        from rq.timeouts import TimerDeathPenalty
        from rq.worker import SimpleWorker

        class WindowsSimpleWorker(SimpleWorker):
            death_penalty_class = TimerDeathPenalty

        worker_cls = WindowsSimpleWorker
        logger.info("Windows detected - using SimpleWorker + TimerDeathPenalty")
    else:
        worker_cls = rq.Worker

    # Start worker (no scheduler - rq_scheduler is not installed)
    worker = worker_cls(["processing"], connection=redis_conn)
    worker.work()


if __name__ == "__main__":
    main()
