"""
로그 스트리밍 API 라우터
"""

import asyncio
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.apps.api.logging.sse_log_handler import get_sse_log_handler
from src.schemas.sse_response import SSEResponse

log_router = APIRouter(prefix="/logs", tags=["로그"])


@log_router.get(
    "/stream",
    summary="서버 로그 실시간 스트리밍",
    description="""
    서버의 로그를 실시간으로 스트리밍합니다.
    
    **주요 기능:**
    - SSE(Server-Sent Events)를 통한 실시간 로그 스트리밍
    - 모든 로그 레벨 지원 (INFO, DEBUG, WARNING, ERROR)
    - 로그 레벨별 색상 구분
    - 자동 연결 관리
    
    **응답 형식:**
    - `text/event-stream` 타입의 SSE 스트림
    - 각 이벤트는 JSON 형태의 로그 데이터 포함
    """,
    responses={
        200: {
            "description": "성공적인 SSE 스트림 응답",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "type": "string",
                        "example": 'data: {"event_type": "SERVER_LOG", "event_data": {"log_level": "INFO", "logger_name": "api", "message": "로그 메시지", "timestamp": "2025-01-01 12:00:00"}}\n\n',
                    }
                }
            },
        },
    },
)
async def stream_server_logs(request: Request) -> StreamingResponse:
    """
    서버 로그를 실시간으로 스트리밍합니다.

    Args:
        request: HTTP 요청 객체

    Returns:
        StreamingResponse: SSE 스트림 응답
    """
    # 구독자 ID 생성
    subscriber_id = str(uuid.uuid4())

    # SSE 로그 핸들러 가져오기
    sse_handler = get_sse_log_handler()

    # 구독자 추가
    log_queue = sse_handler.add_subscriber(subscriber_id)

    async def generate_log_stream() -> AsyncGenerator[str, None]:
        """로그 스트림 생성"""
        try:
            while True:
                # 클라이언트 연결 확인
                if await request.is_disconnected():
                    break

                try:
                    # 로그 큐에서 로그 가져오기 (타임아웃 1초)
                    log_data = await asyncio.wait_for(log_queue.get(), timeout=1.0)

                    # SSE 응답 생성
                    sse_response = SSEResponse.create_server_log(
                        log_level=log_data["log_level"],
                        logger_name=log_data["logger_name"],
                        message=log_data["message"],
                        timestamp=log_data["timestamp"],
                    )

                    # SSE 형식으로 전송
                    yield f"data: {sse_response.model_dump_json()}\n\n"

                except asyncio.TimeoutError:
                    # 타임아웃 시 keep-alive 메시지 전송
                    yield 'data: {"event_type": "KEEP_ALIVE"}\n\n'
                    continue

        except Exception as e:
            # 오류 발생 시 오류 메시지 전송
            error_response = SSEResponse.create_error(str(e))
            yield f"data: {error_response.model_dump_json()}\n\n"

        finally:
            # 구독자 제거
            sse_handler.remove_subscriber(subscriber_id)

    return StreamingResponse(
        generate_log_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
