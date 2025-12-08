"""
Priority Queue for LLM requests
"""

import asyncio
import heapq
import time
import logging
from typing import Any, Callable, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("llm.priority_queue")


@dataclass
class PriorityRequest:
    """우선순위가 있는 요청"""

    priority: int  # 낮은 숫자가 높은 우선순위
    task_type: str  # Task 타입 (의도분석, 최종답변 등)
    timestamp: float = field(default_factory=time.time)  # 요청 시간
    request_id: str = ""  # 요청 ID (디버깅용)
    data: Any = None  # 요청 데이터

    def __lt__(self, other):
        """우선순위 비교 (낮은 숫자가 높은 우선순위)"""
        if self.priority != other.priority:
            return self.priority < other.priority
        # 우선순위가 같으면 먼저 온 요청이 우선
        return self.timestamp < other.timestamp


class PriorityQueue:
    """우선순위 큐"""

    def __init__(self, priority_config: dict):
        """
        Initialize priority queue

        Args:
            priority_config: Task 타입별 우선순위 매핑
        """
        self.priority_config = priority_config
        self.queue: list = []
        self.lock = asyncio.Lock()
        self.total_queued = 0
        self.total_processed = 0

    def get_priority(self, task_type: Optional[str] = None) -> int:
        """
        Get priority for task type

        Args:
            task_type: Task 타입

        Returns:
            Priority value (낮은 숫자가 높은 우선순위)
        """
        if task_type and task_type in self.priority_config:
            return self.priority_config[task_type]
        return self.priority_config.get("default", 5)

    async def put(
        self,
        task_type: Optional[str] = None,
        request_id: str = "",
        data: Any = None,
    ) -> PriorityRequest:
        """
        Add request to queue

        Args:
            task_type: Task 타입
            request_id: 요청 ID
            data: 요청 데이터

        Returns:
            PriorityRequest object
        """
        priority = self.get_priority(task_type)
        request = PriorityRequest(
            priority=priority,
            task_type=task_type or "default",
            request_id=request_id,
            data=data,
        )

        async with self.lock:
            heapq.heappush(self.queue, request)
            self.total_queued += 1
            logger.debug(
                f"[PRIORITY_QUEUE] Request queued: task_type={task_type}, priority={priority}, queue_size={len(self.queue)}"
            )

        return request

    async def get(self) -> PriorityRequest:
        """
        Get next request from queue (highest priority first)

        Returns:
            PriorityRequest object
        """
        async with self.lock:
            if not self.queue:
                raise asyncio.QueueEmpty("Queue is empty")

            request = heapq.heappop(self.queue)
            self.total_processed += 1
            wait_time = time.time() - request.timestamp
            logger.debug(
                f"[PRIORITY_QUEUE] Request dequeued: task_type={request.task_type}, priority={request.priority}, wait_time={wait_time:.2f}s"
            )
            return request

    async def get_nowait(self) -> Optional[PriorityRequest]:
        """
        Get next request from queue without waiting

        Returns:
            PriorityRequest object or None if queue is empty
        """
        try:
            return await self.get()
        except asyncio.QueueEmpty:
            return None

    def qsize(self) -> int:
        """Get queue size"""
        return len(self.queue)

    def get_stats(self) -> dict:
        """Get queue statistics"""
        return {
            "queue_size": len(self.queue),
            "total_queued": self.total_queued,
            "total_processed": self.total_processed,
        }

