"""
QuantX — Celery Async Runtime.

Celery tasks are synchronous callables, but every QuantX service is async. The
naive bridge is ``asyncio.run(coro)`` inside each task, which creates and
destroys an event loop per task. That breaks any pooled resource bound to a
loop: SQLAlchemy's asyncpg connections survive the first task and then raise
"Event loop is closed" or "attached to a different loop" on the second.

This module gives each worker *process* one long-lived event loop, creates the
database engine inside it, and disposes both on shutdown.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

from celery.signals import worker_process_init, worker_process_shutdown

from app.core.database import dispose_engine
from app.core.logging import get_logger
from app.core.redis import close_redis

logger = get_logger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def get_loop() -> asyncio.AbstractEventLoop:
    """Get this worker process's persistent event loop, creating it if needed."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on the worker's persistent loop and return its result."""
    return get_loop().run_until_complete(coro)


@worker_process_init.connect
def _init_worker_process(**_kwargs: Any) -> None:
    """Create the process-local event loop when a worker process forks."""
    get_loop()
    logger.info("celery_worker_process_loop_started")


@worker_process_shutdown.connect
def _shutdown_worker_process(**_kwargs: Any) -> None:
    """Dispose pooled resources before the worker process exits."""
    global _loop
    if _loop is None or _loop.is_closed():
        return
    try:
        _loop.run_until_complete(dispose_engine())
        _loop.run_until_complete(close_redis())
    except Exception as exc:
        logger.warning("celery_worker_shutdown_cleanup_failed", error=str(exc))
    finally:
        _loop.close()
        _loop = None
        logger.info("celery_worker_process_loop_closed")
