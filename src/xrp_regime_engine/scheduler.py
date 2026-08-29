from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable


logger = logging.getLogger(__name__)


async def run_forever(job: Callable[[], Awaitable[None]], interval_seconds: int) -> None:
    """Simple idempotent scheduler loop; production must add distributed locking."""
    if interval_seconds < 1:
        raise ValueError("interval_seconds must be positive")
    while True:
        try:
            await job()
        except Exception:
            logger.exception("scheduled job failed")
        await asyncio.sleep(interval_seconds)
