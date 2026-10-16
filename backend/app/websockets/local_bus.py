"""
QuantX — In-process market-event bus.

On a single-worker deployment the ingestion stream and the WebSocket gateway run
in the same process and the same event loop, so ticks can be handed to clients
directly over asyncio queues — with none of the Redis PUBLISH/SUBSCRIBE traffic
the cross-worker path needs. That traffic (one PUBLISH per upstream tick, dozens
per second) is what exhausts a managed free Redis, and once the quota trips the
gateway's subscription goes silent and live updates stop reaching the browser.

The bus is intentionally tiny: fan a published message out to every subscriber
queue for that symbol. It is single-event-loop only (which is exactly the
single-worker case); cross-process fan-out stays on Redis, selected by
``single_worker_mode``.
"""

import asyncio
from collections import defaultdict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

# Per-subscriber backlog cap. A browser that cannot keep up must not let the
# process buffer ticks without bound; the oldest are dropped, which is the right
# way for a live feed to shed load — freshness over completeness.
QUEUE_MAXSIZE = 1000


class LocalMarketBus:
    """Fan market events out to in-process subscribers, keyed by symbol."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)

    @property
    def subscriber_count(self) -> int:
        """Total live subscriber queues across all symbols (for diagnostics)."""
        return sum(len(qs) for qs in self._subscribers.values())

    def publish(self, symbol: str, message: str) -> None:
        """Deliver a message to every subscriber for ``symbol``.

        Non-blocking: a full queue drops its oldest entry to make room rather
        than stalling the ingestion loop on one slow client.
        """
        queues = self._subscribers.get(symbol.upper())
        if not queues:
            return
        for queue in queues:
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(message)

    @asynccontextmanager
    async def subscribe(self, symbol: str) -> AsyncGenerator["asyncio.Queue[str]"]:
        """Yield a queue receiving every message for ``symbol`` until released."""
        key = symbol.upper()
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAXSIZE)
        self._subscribers[key].add(queue)
        try:
            yield queue
        finally:
            subscribers = self._subscribers.get(key)
            if subscribers is not None:
                subscribers.discard(queue)
                if not subscribers:
                    self._subscribers.pop(key, None)


# Process-wide bus shared by the ingestion stream and the WebSocket gateway.
market_bus = LocalMarketBus()
