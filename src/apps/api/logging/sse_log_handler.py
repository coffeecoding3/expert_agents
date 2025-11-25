"""
SSE 로그 핸들러 - 서버 로그를 SSE로 스트리밍
"""

import asyncio
import json
import logging
from datetime import datetime
from logging import LogRecord
from typing import Any, Dict, Optional


class SSELogHandler(logging.Handler):
    """SSE로 로그를 스트리밍하는 로그 핸들러"""

    def __init__(self):
        super().__init__()
        self.log_queue = asyncio.Queue()
        self.subscribers: Dict[str, asyncio.Queue] = {}

    def emit(self, record: LogRecord):
        """로그 레코드를 큐에 추가"""
        try:
            # 로그 레코드를 딕셔너리로 변환
            log_data = {
                "timestamp": datetime.fromtimestamp(record.created).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "log_level": record.levelname,
                "logger_name": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "funcName": record.funcName,
                "lineno": record.lineno,
            }

            # 비동기 큐에 추가 (논블로킹)
            try:
                self.log_queue.put_nowait(log_data)
            except asyncio.QueueFull:
                # 큐가 가득 찬 경우 오래된 로그 제거
                try:
                    self.log_queue.get_nowait()
                    self.log_queue.put_nowait(log_data)
                except asyncio.QueueEmpty:
                    pass

        except Exception:
            # 로그 핸들러에서 예외가 발생해도 무시
            pass

    async def get_log(self) -> Optional[Dict[str, Any]]:
        """로그 큐에서 로그를 가져옴"""
        try:
            return await asyncio.wait_for(self.log_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return None

    def add_subscriber(self, subscriber_id: str) -> asyncio.Queue:
        """새로운 구독자 추가"""
        queue = asyncio.Queue(maxsize=100)
        self.subscribers[subscriber_id] = queue
        return queue

    def remove_subscriber(self, subscriber_id: str):
        """구독자 제거"""
        if subscriber_id in self.subscribers:
            del self.subscribers[subscriber_id]

    async def broadcast_log(self, log_data: Dict[str, Any]):
        """모든 구독자에게 로그 브로드캐스트"""
        if not self.subscribers:
            return

        # 구독자별로 로그 전송
        for subscriber_id, queue in list(self.subscribers.items()):
            try:
                queue.put_nowait(log_data)
            except asyncio.QueueFull:
                # 큐가 가득 찬 경우 구독자 제거
                self.remove_subscriber(subscriber_id)

    async def start_broadcast_loop(self):
        """로그 브로드캐스트 루프 시작"""
        while True:
            try:
                log_data = await self.get_log()
                if log_data:
                    await self.broadcast_log(log_data)
            except Exception:
                # 브로드캐스트 루프에서 예외가 발생해도 계속 실행
                pass


# 전역 SSE 로그 핸들러 인스턴스
sse_log_handler = SSELogHandler()


def setup_sse_logging():
    """SSE 로깅 설정"""
    # 루트 로거에 SSE 핸들러 추가 (중복 방지)
    root_logger = logging.getLogger()
    sse_log_handler.setLevel(logging.INFO)
    
    # 이미 SSE 핸들러가 추가되어 있는지 확인
    has_sse_handler = any(h == sse_log_handler for h in root_logger.handlers)
    if not has_sse_handler:
        root_logger.addHandler(sse_log_handler)

    # 브로드캐스트 루프 시작 (이벤트 루프가 실행 중일 때만)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(sse_log_handler.start_broadcast_loop())
    except RuntimeError:
        # 이벤트 루프가 실행 중이 아닌 경우, 나중에 시작하도록 예약
        pass


def get_sse_log_handler() -> SSELogHandler:
    """SSE 로그 핸들러 인스턴스 반환"""
    return sse_log_handler
