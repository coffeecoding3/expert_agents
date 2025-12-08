"""
Rate Limiter for LLM requests
"""

import asyncio
import time
import logging
from collections import deque
from typing import Optional

logger = logging.getLogger("llm.rate_limiter")


class RateLimiter:
    """Rate limiter for controlling request rate"""

    def __init__(self, max_requests_per_minute: int = 500000):
        """
        Initialize rate limiter

        Args:
            max_requests_per_minute: Maximum requests per minute
        """
        self.max_requests_per_minute = max_requests_per_minute
        self.request_times: deque = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """
        Acquire permission to make a request

        Returns:
            True if request is allowed, False if rate limit exceeded
        """
        if self.max_requests_per_minute >= 500000:
            # 사실상 제한 없음
            return True

        async with self.lock:
            now = time.time()
            # 1분 이전의 요청 기록 제거
            while self.request_times and self.request_times[0] < now - 60:
                self.request_times.popleft()

            # 요청 수 체크
            if len(self.request_times) >= self.max_requests_per_minute:
                logger.warning(
                    f"[RATE_LIMITER] Rate limit exceeded: {len(self.request_times)}/{self.max_requests_per_minute} requests in the last minute"
                )
                return False

            # 요청 시간 기록
            self.request_times.append(now)
            return True

    async def wait_if_needed(self):
        """
        Wait if rate limit is reached
        """
        if self.max_requests_per_minute >= 500000:
            return

        async with self.lock:
            now = time.time()
            # 1분 이전의 요청 기록 제거
            while self.request_times and self.request_times[0] < now - 60:
                self.request_times.popleft()

            # 요청 수 체크
            if len(self.request_times) >= self.max_requests_per_minute:
                # 가장 오래된 요청이 만료될 때까지 대기
                oldest_request_time = self.request_times[0]
                wait_time = 60 - (now - oldest_request_time) + 0.1  # 0.1초 여유
                if wait_time > 0:
                    logger.info(
                        f"[RATE_LIMITER] Rate limit reached, waiting {wait_time:.2f} seconds"
                    )
                    await asyncio.sleep(wait_time)

            # 요청 시간 기록
            self.request_times.append(time.time())

    def get_current_rate(self) -> float:
        """
        Get current request rate (requests per minute)

        Returns:
            Current request rate
        """
        now = time.time()
        # 1분 이전의 요청 기록 제거
        while self.request_times and self.request_times[0] < now - 60:
            self.request_times.popleft()

        return len(self.request_times)

