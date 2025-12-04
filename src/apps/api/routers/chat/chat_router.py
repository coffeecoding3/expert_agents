"""
Chat Router for Expert Agent Service

SSE 기반 채팅 인터페이스
"""

import asyncio
import json
import os
from logging import getLogger
from typing import Any, AsyncGenerator, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from src.database.connection import get_database_session
from src.database.models import ChatChannelStatus, MessageType
from src.database.services import chat_channel_service, chat_message_service
from src.database.services.lgenie_sync_service import lgenie_sync_service
from src.utils.log_collector import collector

from .chat_generator import ChatResponseGenerator
from .chat_models import ChatRequest
from .stream_manager import stream_manager

logger = getLogger("chat")


# main.py에서 생성된 오케스트레이터 팩토리를 가져오기 위한 의존성
def get_orchestrator_factory(request: Request):
    return request.app.state.orchestrator_factory


# 동적 에이전트 라우터 (path parameter 사용)
agent_router = APIRouter(
    prefix="/{agent_code}/api/v1/chat",
    tags=["AI 에이전트 채팅"],
    responses={
        404: {"description": "에이전트를 찾을 수 없습니다"},
        500: {"description": "서버 내부 오류"},
    },
)


async def get_or_create_chat_channel(
    db: Session, session_id: str, user_id: str, agent_code: str, question: str
):
    """채팅방을 조회하거나 생성합니다."""
    try:
        # LGenie 존재 여부
        lgenie_exists = lgenie_sync_service.check_chat_group_exists(session_id)

        # 기존 채널 조회 또는 생성
        channel = chat_channel_service.get_by_session_id(db, session_id)
        if channel:
            lgenie_sync_service.ensure_lgenie_prereqs(
                session_id,
                str(channel.user_id),
                agent_code,
                channel.created_at,
                channel.updated_at,
                "ensure_group_and_chat",
            )
            return channel

        # 새 채팅방 생성
        numeric_user_id = await _get_numeric_user_id(db, user_id)
        agent_id = await _get_agent_id(db, agent_code)

        # 제목 결정
        title = f"채팅 {session_id[:8]}..." if lgenie_exists else f"test_{session_id}"

        channel = chat_channel_service.create_channel(
            db,
            session_id=session_id,
            user_id=numeric_user_id,
            agent_id=agent_id,
            title=title,
            status=ChatChannelStatus.ACTIVE,
            channel_metadata={
                "agent_code": agent_code,
                "first_question": question[:100],
                "lgenie_exists": lgenie_exists,
            },
        )
        # 채널 생성 후 LGenie 선행 조건 보장
        if channel:
            lgenie_sync_service.ensure_lgenie_prereqs(
                session_id,
                str(channel.user_id),
                agent_code,
                channel.created_at,
                channel.updated_at,
                "ensure_group_and_chat",
            )
        return channel

    except Exception as e:
        logger.error(f"채팅방 조회/생성 실패: {e}")
        return None


async def _get_numeric_user_id(db: Session, user_id: str) -> int:
    """사용자 ID를 숫자 ID로 변환합니다."""
    try:
        return int(user_id)
    except ValueError:
        try:
            from src.database.services import database_service

            if database_service.is_available():
                user_record = database_service.select_one(
                    "users", "id", "user_id = %s", (user_id,)
                )
                return user_record["id"] if user_record else 1
            return 1
        except Exception as e:
            logger.error(f"사용자 ID 조회 실패: {e}")
            return 1


async def _get_agent_id(db: Session, agent_code: str) -> int:
    """에이전트 코드로 에이전트 ID를 조회합니다."""
    try:
        from src.database.services import database_service

        if database_service.is_available():
            agent_record = database_service.select_one(
                "agents", "id", "code = %s AND is_active = 1", (agent_code,)
            )
            return agent_record["id"] if agent_record else 1
        return 1
    except Exception as e:
        logger.error(f"에이전트 ID 조회 실패: {e}")
        return 1


async def save_user_message(
    db: Session,
    channel_id: int,
    content: str,
    agent_id: int,
    message_metadata: dict = None,
):
    """사용자 메시지를 저장합니다."""
    try:
        msg = chat_message_service.create(
            db,
            channel_id=channel_id,
            agent_id=agent_id,
            message_type=MessageType.USER,
            content=content,
            message_metadata=message_metadata or {},
        )
        try:
            if msg:
                lgenie_sync_service.sync_chat_message(msg, db)
        except Exception as e:
            logger.warning(f"LGenie 메시지 동기화 실패(무시됨): {e}")
        return msg
    except Exception as e:
        logger.error(f"사용자 메시지 저장 실패: {e}")
        return None


async def generate_chat_response(
    orchestrator_factory,
    question: str,
    user_id: str,
    agent_code: str = "caia",
    session_id: str | None = None,
    db: Session = None,
    client_id: str | None = None,
    tools: Optional[List[str]] = None,
) -> AsyncGenerator[str, None]:
    """오케스트레이터를 사용하여 채팅 응답 생성 (SSE 스트리밍)"""

    # 에이전트별 오케스트레이터 가져오기
    orchestrator = orchestrator_factory.get_orchestrator(agent_code)

    if orchestrator is None:
        logger.error(f"{agent_code} 에이전트용 오케스트레이터를 찾을 수 없습니다.")
        yield f"data: {json.dumps({'type': 'error', 'content': f'{agent_code} 에이전트를 찾을 수 없습니다.'})}\n\n"
        return

    # 채팅방 조회 또는 생성
    channel = None
    user_message = None

    if db and session_id:
        try:
            channel = await get_or_create_chat_channel(
                db, session_id, user_id, agent_code, question
            )

            if channel:
                # 에이전트 ID 조회
                agent_id = await _get_agent_id(db, agent_code)

                # 사용자 메시지 저장
                user_message = await save_user_message(
                    db,
                    channel.id,
                    question,
                    agent_id,
                    {
                        "total_token": len(question.split()),  # 간소화된 메타데이터
                        "model": ["user_input"],  # 사용자 입력은 모델이 없음
                    },
                )
                # 메시지 동기화는 save_user_message 내부에서 수행됨
            else:
                # LGenie DB에 chat_group_id가 존재하지 않는 경우 - Main DB에만 저장된 상태
                logger.info(
                    f"LGenie DB 없음 - Main DB에만 저장된 채널 사용: session_id={session_id}"
                )
                # 에러를 반환하지 않고 정상 진행
        except Exception as e:
            logger.error(f"채팅방/메시지 저장 실패: {e}")

    # ChatResponseGenerator 인스턴스 생성하여 처리
    generator = ChatResponseGenerator(agent_code)

    # 채팅방과 사용자 메시지 정보를 generator에 전달
    if channel:
        generator.channel_id = channel.id
        generator.user_message_id = user_message.id if user_message else None
        collector.log("channel_id", generator.channel_id)
        collector.log("user_message_id", generator.user_message_id)

    async for sse_data in generator.generate_response(
        orchestrator=orchestrator,
        question=question,
        user_id=user_id,
        session_id=session_id,
        db=db,  # 데이터베이스 세션 전달
        client_id=client_id,  # 클라이언트 ID 전달
        tools=tools,  # 도구 목록 전달
    ):
        yield sse_data


# =============================================================================
# 동적 에이전트 라우터 (path parameter 사용)
# =============================================================================


@agent_router.post(
    "/stream",
    summary="AI 에이전트와 실시간 채팅",
    description="""
    AI 에이전트와 실시간으로 채팅을 진행합니다.
    
    **주요 기능:**
    - SSE(Server-Sent Events)를 통한 실시간 스트리밍 응답
    - 에이전트별 맞춤형 응답 생성
    - 채팅 히스토리 자동 저장
    - 세션 기반 대화 관리
    
    **요청 형식:**
    ```json
    {
        "question": "사용자 질문",
        "user_id": "사용자 ID",
        "chat_group_id": "세션 ID (채팅방 식별자)"
    }
    ```
    
    **응답 형식:**
    - `text/event-stream` 타입의 SSE 스트림
    - 각 이벤트는 JSON 형태의 데이터 포함
    - `done: true`로 스트림 종료 표시
    """,
    responses={
        200: {
            "description": "성공적인 SSE 스트림 응답",
            "content": {
                "text/event-stream": {
                    "schema": {
                        "type": "string",
                        "example": 'data: {"type": "llm", "token": "안녕하세요", "done": false}\n\n',
                    }
                }
            },
        },
        400: {
            "description": "잘못된 요청",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "필수 필드가 누락되었습니다",
                            }
                        },
                    }
                }
            },
        },
        500: {
            "description": "서버 내부 오류",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "처리 중 오류가 발생했습니다",
                            }
                        },
                    }
                }
            },
        },
    },
    tags=["채팅"],
)
async def dynamic_agent_chat_stream(
    agent_code: str,
    chat_req: ChatRequest,
    request: Request,
    tools: Optional[str] = Query(
        None,
        description="사용할 도구 목록 (쉼표로 구분): gemini_web_search,llm_knowledge,internal_knowledge",
        include_in_schema=True,
    ),
    orchestrator_factory=Depends(get_orchestrator_factory),
    db: Session = Depends(get_database_session),
):
    """
    AI 에이전트와 실시간 채팅을 진행합니다.

    Args:
        agent_code: 에이전트 코드 (예: caia, discussion, search)
        chat_req: 채팅 요청 데이터
        request: HTTP 요청 객체
        orchestrator_factory: 오케스트레이터 팩토리
        db: 데이터베이스 세션

    Returns:
        StreamingResponse: SSE 스트림 응답
    """
    logger.info(f"채팅요청: {agent_code} - {chat_req.user_id} - {chat_req.question}")

    # 요청 데이터 추출
    user_query = chat_req.question
    user_id = chat_req.user_id
    session_id = chat_req.chat_group_id
    cookie_sid = request.cookies.get(os.getenv("SESSION_COOKIE_NAME", "sid"))
    final_session_id = session_id or cookie_sid or None

    # Tools 파라미터 파싱
    tools_list = None
    if tools:
        tools_list = [t.strip() for t in tools.split(",") if t.strip()]
        collector.log("tools", tools_list)

    # 클라이언트 ID 생성 (요청별 고유 식별자)
    import uuid

    client_id = str(uuid.uuid4())

    collector.log("user_query", user_query)
    collector.log("user_id", user_id)
    collector.log("session_id", session_id)
    collector.log("cookie_sid", cookie_sid)
    collector.log("final_session_id", final_session_id)
    collector.log("client_id", client_id)

    # db가 제너레이터인 경우 처리
    db_session = next(db) if hasattr(db, "__next__") else db

    async def safe_generate_response():
        """안전한 응답 생성기 - CancelledError 처리"""
        try:
            # 클라이언트 연결 상태 확인
            if await request.is_disconnected():
                return

            async for chunk in generate_chat_response(
                orchestrator_factory,
                user_query,
                user_id,
                agent_code=agent_code,
                session_id=final_session_id,
                db=db_session,
                client_id=client_id,
                tools=tools_list,
            ):
                # 클라이언트 연결 상태 주기적 확인
                if await request.is_disconnected():
                    break

                # chunk가 코루틴인 경우 await 처리
                if asyncio.iscoroutine(chunk):
                    chunk = await chunk

                yield chunk
        except asyncio.CancelledError:
            logger.warning(f"{agent_code} 요청 취소됨")
            # 클라이언트 연결 해제 시 스트림에서 제거
            if final_session_id and client_id:
                stream_manager.remove_client_from_stream(final_session_id, client_id)
            yield f"data: {json.dumps({'type': 'error', 'content': '요청이 취소되었습니다.'})}\n\n"
        except Exception as e:
            logger.error(f"{agent_code} 채팅 응답 생성 중 오류: {e}")
            # 오류 발생 시에도 클라이언트 제거
            if final_session_id and client_id:
                stream_manager.remove_client_from_stream(final_session_id, client_id)
            yield f"data: {json.dumps({'type': 'error', 'content': f'처리 중 오류가 발생했습니다: {str(e)}'})}\n\n"

    return StreamingResponse(
        safe_generate_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@agent_router.get(
    "/health",
    summary="에이전트 채팅 서비스 상태 확인",
    description="""
    특정 에이전트의 채팅 서비스 상태를 확인합니다.
    
    **응답 정보:**
    - 서비스 상태 (healthy/unhealthy)
    - 에이전트 코드
    - 서비스 이름
    - 현재 타임스탬프
    """,
    responses={
        200: {
            "description": "서비스 상태 정보",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "example": "healthy"},
                            "service": {
                                "type": "string",
                                "example": "CAIA Chat Service",
                            },
                            "agent_code": {"type": "string", "example": "caia"},
                            "timestamp": {"type": "number", "example": 1703123456.789},
                        },
                    }
                }
            },
        }
    },
    tags=["상태 확인"],
)
async def dynamic_agent_chat_health(agent_code: str) -> Dict[str, Any]:
    """
    에이전트 채팅 서비스의 상태를 확인합니다.

    Args:
        agent_code: 확인할 에이전트 코드

    Returns:
        Dict[str, Any]: 서비스 상태 정보
    """
    return {
        "status": "healthy",
        "service": f"{agent_code.upper()} Chat Service",
        "agent_code": agent_code,
        "timestamp": asyncio.get_event_loop().time(),
    }


@agent_router.get(
    "/streams",
    summary="활성 스트림 상태 조회",
    description="""
    현재 활성화된 스트림들의 상태를 조회합니다.
    
    **응답 정보:**
    - 활성 스트림 목록
    - 각 스트림의 상태 정보
    - 연결된 클라이언트 수
    """,
    responses={
        200: {
            "description": "활성 스트림 정보",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "active_streams": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "chat_group_id": {"type": "string"},
                                        "agent_code": {"type": "string"},
                                        "user_id": {"type": "string"},
                                        "connected_clients": {"type": "number"},
                                        "is_active": {"type": "boolean"},
                                        "created_at": {"type": "string"},
                                        "last_activity": {"type": "string"},
                                    },
                                },
                            },
                            "total_count": {"type": "number"},
                        },
                    }
                }
            },
        }
    },
    tags=["스트림 관리"],
)
async def get_active_streams() -> Dict[str, Any]:
    """
    활성 스트림 상태를 조회합니다.

    Returns:
        Dict[str, Any]: 활성 스트림 정보
    """
    active_streams = stream_manager.get_active_streams()
    stream_info = []

    for chat_group_id, stream_state in active_streams.items():
        stream_info.append(stream_state.to_dict())

    return {
        "active_streams": stream_info,
        "total_count": len(stream_info),
    }


@agent_router.get(
    "/streams/{chat_group_id}",
    summary="특정 스트림 상태 조회",
    description="""
    특정 chat_group_id의 스트림 상태를 조회합니다.
    """,
    responses={
        200: {
            "description": "스트림 상태 정보",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "chat_group_id": {"type": "string"},
                            "agent_code": {"type": "string"},
                            "user_id": {"type": "string"},
                            "connected_clients": {"type": "number"},
                            "is_active": {"type": "boolean"},
                            "created_at": {"type": "string"},
                            "last_activity": {"type": "string"},
                        },
                    }
                }
            },
        },
        404: {
            "description": "스트림을 찾을 수 없음",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "스트림을 찾을 수 없습니다",
                            }
                        },
                    }
                }
            },
        },
    },
    tags=["스트림 관리"],
)
async def get_stream_info(chat_group_id: str) -> Dict[str, Any]:
    """
    특정 스트림의 상태를 조회합니다.

    Args:
        chat_group_id: 조회할 스트림의 chat_group_id

    Returns:
        Dict[str, Any]: 스트림 상태 정보
    """
    stream_info = stream_manager.get_stream_info(chat_group_id)
    if not stream_info:
        raise HTTPException(status_code=404, detail="스트림을 찾을 수 없습니다")

    return stream_info
