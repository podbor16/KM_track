import asyncio
import json
from typing import Optional


class TrackerHub:
    """Per-event SSE хаб: рассылает полные данные трекера всем подключённым клиентам."""

    def __init__(self):
        self._subs: dict[int, set[asyncio.Queue]] = {}

    async def subscribe(self, event_id: int) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=5)
        self._subs.setdefault(event_id, set()).add(queue)
        return queue

    def unsubscribe(self, event_id: int, queue: asyncio.Queue) -> None:
        self._subs.get(event_id, set()).discard(queue)

    async def broadcast(self, event_id: int, data: str) -> None:
        slow: set = set()
        for q in self._subs.get(event_id, set()):
            try:
                q.put_nowait(data)
            except asyncio.QueueFull:
                slow.add(q)
        self._subs.get(event_id, set()).difference_update(slow)

    def total_sse_count(self) -> int:
        """Суммарное число активных SSE-подписчиков по всем event_id."""
        return sum(len(queues) for queues in self._subs.values())


class NotificationHub:
    """Глобальный SSE хаб: лёгкие уведомления {type, ...payload} для results/startlist."""

    def __init__(self):
        self._queues: set[asyncio.Queue] = set()

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=20)
        self._queues.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._queues.discard(queue)

    async def broadcast(self, event_type: str, payload: Optional[dict] = None) -> None:
        message = json.dumps({"type": event_type, **(payload or {})})
        slow: set = set()
        for q in self._queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                slow.add(q)
        self._queues -= slow


tracker_hub = TrackerHub()
notification_hub = NotificationHub()
