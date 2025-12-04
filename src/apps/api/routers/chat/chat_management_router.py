"""
Chat Management Router for Expert Agent Service

채팅 채널 및 메시지 관리 API
"""

from logging import getLogger
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.database.connection import get_database_session
from src.database.models import ChatChannel, ChatMessage
from src.database.services import chat_channel_service, chat_message_service

from .chat_models import (
    ChatChannelListResponse,
    ChatChannelResponse,
    ChatChannelWithMessagesResponse,
    ChatMessageResponse,
)

logger = getLogger("chat_management")

# 채팅 관리 라우터
chat_management_router = APIRouter(
    prefix="/api/v1/chat",
    tags=["채팅 관리"],
    responses={
        404: {"description": "리소스를 찾을 수 없습니다"},
        500: {"description": "서버 내부 오류"},
    },
)


@chat_management_router.get(
    "/channels",
    response_model=ChatChannelListResponse,
    summary="채팅 채널 목록 조회",
    description="""
    사용자의 채팅 채널 목록을 조회합니다.
    
    **주요 기능:**
    - 사용자별 채팅 채널 목록 조회
    - 페이지네이션 지원
    - 에이전트별 필터링 가능
    - 최신 메시지 순으로 정렬
    
    **쿼리 파라미터:**
    - `user_id`: 사용자 ID (필수)
    - `agent_code`: 에이전트 코드 (선택)
    - `page`: 페이지 번호 (기본값: 1)
    - `page_size`: 페이지 크기 (기본값: 20, 최대: 100)
    - `status`: 채널 상태 필터 (active, inactive, archived)
    """,
    responses={
        200: {
            "description": "채팅 채널 목록 조회 성공",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "channels": {
                                "type": "array",
                                "items": {
                                    "$ref": "#/components/schemas/ChatChannelResponse"
                                },
                            },
                            "total_count": {"type": "integer", "example": 15},
                            "page": {"type": "integer", "example": 1},
                            "page_size": {"type": "integer", "example": 20},
                        },
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
                                "example": "user_id는 필수입니다",
                            }
                        },
                    }
                }
            },
        },
    },
)
async def get_chat_channels(
    user_id: str = Query(..., description="사용자 ID"),
    agent_code: Optional[str] = Query(None, description="에이전트 코드"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    status: Optional[str] = Query(
        None, description="채널 상태 (active, inactive, archived)"
    ),
    db: Session = Depends(get_database_session),
) -> ChatChannelListResponse:
    """
    사용자의 채팅 채널 목록을 조회합니다.

    Args:
        user_id: 사용자 ID
        agent_code: 에이전트 코드 (선택)
        page: 페이지 번호
        page_size: 페이지 크기
        status: 채널 상태 필터
        db: 데이터베이스 세션

    Returns:
        ChatChannelListResponse: 채팅 채널 목록
    """
    try:
        # 사용자 ID를 숫자 ID로 변환
        numeric_user_id = await _get_numeric_user_id(db, user_id)

        # 에이전트 ID 조회 (agent_code가 제공된 경우)
        agent_id = None
        if agent_code:
            agent_id = await _get_agent_id(db, agent_code)

        # 채팅 채널 목록 조회
        channels, total_count = chat_channel_service.get_user_channels(
            db,
            user_id=numeric_user_id,
            agent_id=agent_id,
            status=status,
            page=page,
            page_size=page_size,
        )

        # 응답 모델로 변환
        channel_responses = [
            ChatChannelResponse(
                id=channel.id,
                session_id=channel.session_id,
                user_id=channel.user_id,
                agent_id=channel.agent_id,
                title=channel.title,
                status=channel.status.value,
                channel_metadata=channel.channel_metadata,
                last_message_at=channel.last_message_at,
                message_count=channel.message_count,
                created_at=channel.created_at,
                updated_at=channel.updated_at,
            )
            for channel in channels
        ]

        return ChatChannelListResponse(
            channels=channel_responses,
            total_count=total_count,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"[CHAT_MANAGEMENT] 채널 목록 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"채널 목록 조회 중 오류가 발생했습니다: {str(e)}",
        )


@chat_management_router.get(
    "/channels/{session_id}",
    response_model=ChatChannelWithMessagesResponse,
    summary="채팅 채널 상세 조회",
    description="""
    특정 채팅 채널의 상세 정보와 메시지 목록을 조회합니다.
    
    **주요 기능:**
    - 채팅 채널 기본 정보 조회
    - 채널의 모든 메시지 목록 조회
    - 메시지 타입별 필터링 가능
    - 시간순 정렬
    
    **경로 파라미터:**
    - `session_id`: 채팅 세션 ID
    
    **쿼리 파라미터:**
    - `message_type`: 메시지 타입 필터 (user, assistant, system, tool)
    - `limit`: 메시지 수 제한 (기본값: 100, 최대: 500)
    - `offset`: 메시지 오프셋 (기본값: 0)
    """,
    responses={
        200: {
            "description": "채팅 채널 상세 조회 성공",
            "content": {
                "application/json": {
                    "schema": {
                        "$ref": "#/components/schemas/ChatChannelWithMessagesResponse"
                    }
                }
            },
        },
        404: {
            "description": "채팅 채널을 찾을 수 없습니다",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "detail": {
                                "type": "string",
                                "example": "채팅 채널을 찾을 수 없습니다",
                            }
                        },
                    }
                }
            },
        },
    },
)
async def get_chat_channel(
    session_id: str,
    message_type: Optional[str] = Query(None, description="메시지 타입 필터"),
    limit: int = Query(100, ge=1, le=500, description="메시지 수 제한"),
    offset: int = Query(0, ge=0, description="메시지 오프셋"),
    db: Session = Depends(get_database_session),
) -> ChatChannelWithMessagesResponse:
    """
    특정 채팅 채널의 상세 정보와 메시지 목록을 조회합니다.

    Args:
        session_id: 채팅 세션 ID
        message_type: 메시지 타입 필터
        limit: 메시지 수 제한
        offset: 메시지 오프셋
        db: 데이터베이스 세션

    Returns:
        ChatChannelWithMessagesResponse: 채팅 채널 상세 정보
    """
    try:
        # 채팅 채널 조회
        channel = chat_channel_service.get_by_session_id(db, session_id)
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="채팅 채널을 찾을 수 없습니다",
            )

        # 메시지 목록 조회
        messages = chat_message_service.get_channel_messages(
            db,
            channel_id=channel.id,
            message_type=message_type,
            limit=limit,
            offset=offset,
        )

        # 응답 모델로 변환
        message_responses = [
            ChatMessageResponse(
                id=message.id,
                channel_id=message.channel_id,
                agent_id=message.agent_id,
                message_type=message.message_type.value,
                content=message.content,
                message_metadata=message.message_metadata,
                parent_message_id=message.parent_message_id,
                is_deleted=message.is_deleted,
                created_at=message.created_at,
                updated_at=message.updated_at,
            )
            for message in messages
        ]

        return ChatChannelWithMessagesResponse(
            id=channel.id,
            session_id=channel.session_id,
            user_id=channel.user_id,
            agent_id=channel.agent_id,
            title=channel.title,
            status=channel.status.value,
            channel_metadata=channel.channel_metadata,
            last_message_at=channel.last_message_at,
            message_count=channel.message_count,
            created_at=channel.created_at,
            updated_at=channel.updated_at,
            messages=message_responses,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAT_MANAGEMENT] 채널 상세 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"채널 상세 조회 중 오류가 발생했습니다: {str(e)}",
        )


@chat_management_router.get(
    "/channels/{session_id}/messages",
    response_model=List[ChatMessageResponse],
    summary="채팅 메시지 목록 조회",
    description="""
    특정 채팅 채널의 메시지 목록을 조회합니다.
    
    **주요 기능:**
    - 채팅 채널의 메시지 목록 조회
    - 메시지 타입별 필터링
    - 페이지네이션 지원
    - 시간순 정렬
    
    **경로 파라미터:**
    - `session_id`: 채팅 세션 ID
    
    **쿼리 파라미터:**
    - `message_type`: 메시지 타입 필터 (user, assistant, system, tool)
    - `page`: 페이지 번호 (기본값: 1)
    - `page_size`: 페이지 크기 (기본값: 50, 최대: 200)
    """,
    responses={
        200: {
            "description": "메시지 목록 조회 성공",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ChatMessageResponse"},
                    }
                }
            },
        },
        404: {"description": "채팅 채널을 찾을 수 없습니다"},
    },
)
async def get_chat_messages(
    session_id: str,
    message_type: Optional[str] = Query(None, description="메시지 타입 필터"),
    page: int = Query(1, ge=1, description="페이지 번호"),
    page_size: int = Query(50, ge=1, le=200, description="페이지 크기"),
    db: Session = Depends(get_database_session),
) -> List[ChatMessageResponse]:
    """
    특정 채팅 채널의 메시지 목록을 조회합니다.

    Args:
        session_id: 채팅 세션 ID
        message_type: 메시지 타입 필터
        page: 페이지 번호
        page_size: 페이지 크기
        db: 데이터베이스 세션

    Returns:
        List[ChatMessageResponse]: 메시지 목록
    """
    try:
        # 채팅 채널 조회
        channel = chat_channel_service.get_by_session_id(db, session_id)
        if not channel:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="채팅 채널을 찾을 수 없습니다",
            )

        # 메시지 목록 조회
        offset = (page - 1) * page_size
        messages = chat_message_service.get_channel_messages(
            db,
            channel_id=channel.id,
            message_type=message_type,
            limit=page_size,
            offset=offset,
        )

        # 응답 모델로 변환
        return [
            ChatMessageResponse(
                id=message.id,
                channel_id=message.channel_id,
                agent_id=message.agent_id,
                message_type=message.message_type.value,
                content=message.content,
                message_metadata=message.message_metadata,
                parent_message_id=message.parent_message_id,
                is_deleted=message.is_deleted,
                created_at=message.created_at,
                updated_at=message.updated_at,
            )
            for message in messages
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[CHAT_MANAGEMENT] 메시지 목록 조회 실패: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"메시지 목록 조회 중 오류가 발생했습니다: {str(e)}",
        )


async def _get_numeric_user_id(db: Session, user_id: str) -> int:
    """사용자 ID를 숫자 ID로 변환합니다."""
    try:
        # 먼저 숫자인지 확인
        numeric_id = int(user_id)
        return numeric_id
    except ValueError:
        # 문자열인 경우 데이터베이스에서 ID 조회
        try:
            from src.database.services import database_service

            if database_service.is_available():
                user_record = database_service.select_one(
                    "users", "id", "user_id = %s", (user_id,)
                )
                if user_record:
                    return user_record["id"]
            return 1  # 기본값
        except Exception as e:
            logger.error(f"[CHAT_MANAGEMENT] 사용자 ID 조회 실패: {e}")
            return 1


async def _get_agent_id(db: Session, agent_code: str) -> int:
    """에이전트 코드로 에이전트 ID를 조회합니다."""
    try:
        from src.database.services import database_service

        if database_service.is_available():
            agent_record = database_service.select_one(
                "agents", "id", "code = %s AND is_active = 1", (agent_code,)
            )
            if agent_record:
                return agent_record["id"]
        return 1  # 기본값
    except Exception as e:
        logger.error(f"[CHAT_MANAGEMENT] 에이전트 ID 조회 실패: {e}")
        return 1
