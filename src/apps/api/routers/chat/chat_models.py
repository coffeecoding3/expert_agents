"""
Chat Models for Expert Agent Service

채팅 관련 데이터 모델 정의
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """
    채팅 요청 모델

    AI 에이전트와의 채팅을 위한 요청 데이터 구조입니다.
    간소화된 구조로 필수 정보만 포함합니다.
    """

    question: str = Field(
        ...,
        description="사용자가 AI 에이전트에게 질문하는 내용",
        example="LG전자의 최신 스마트폰 기술에 대해 알려주세요",
        min_length=1,
        max_length=2000,
    )

    user_id: str = Field(
        ...,
        description="사용자를 식별하는 고유 ID",
        example="hq15",
        min_length=1,
        max_length=100,
    )

    chat_group_id: str = Field(
        "",
        description="채팅 세션을 식별하는 고유 ID (session_id로 사용됨)",
        example="092ff3a4-7a2d-40f3-9518-95d1d352bdb2",
        max_length=255,
    )

    class Config:
        json_schema_extra = {
            "example": {
                "question": "LG전자의 최신 스마트폰 기술에 대해 알려주세요",
                "user_id": "hq15",
                "chat_group_id": "092ff3a4-7a2d-40f3-9518-95d1d352bdb2",
            }
        }


class ChatMessageResponse(BaseModel):
    """채팅 메시지 응답 모델"""

    id: int = Field(..., description="메시지 ID")
    channel_id: int = Field(..., description="채팅방 ID")
    agent_id: int = Field(..., description="에이전트 ID")
    message_type: str = Field(
        ..., description="메시지 타입 (user, assistant, system, tool)"
    )
    content: str = Field(..., description="메시지 내용")
    message_metadata: Optional[Dict[str, Any]] = Field(
        None, description="메시지 메타데이터"
    )
    parent_message_id: Optional[int] = Field(
        None, description="부모 메시지 ID (답변 관계)"
    )
    is_deleted: bool = Field(False, description="삭제 여부")
    created_at: datetime = Field(..., description="생성 시간")
    updated_at: datetime = Field(..., description="수정 시간")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 123,
                "channel_id": 45,
                "agent_id": 1,
                "message_type": "user",
                "content": "LG전자의 최신 스마트폰 기술에 대해 알려주세요",
                "message_metadata": {"total_token": 15, "model": ["user_input"]},
                "parent_message_id": None,
                "is_deleted": False,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
            }
        }


class ChatChannelResponse(BaseModel):
    """채팅 채널 응답 모델"""

    id: int = Field(..., description="채팅방 ID")
    session_id: str = Field(..., description="세션 ID")
    user_id: int = Field(..., description="사용자 ID")
    agent_id: int = Field(..., description="에이전트 ID")
    title: Optional[str] = Field(None, description="채팅방 제목")
    status: str = Field(..., description="채팅방 상태 (active, inactive, archived)")
    channel_metadata: Optional[Dict[str, Any]] = Field(
        None, description="채팅방 메타데이터"
    )
    last_message_at: Optional[datetime] = Field(None, description="마지막 메시지 시간")
    message_count: int = Field(0, description="메시지 수")
    created_at: datetime = Field(..., description="생성 시간")
    updated_at: datetime = Field(..., description="수정 시간")

    class Config:
        json_schema_extra = {
            "example": {
                "id": 45,
                "session_id": "092ff3a4-7a2d-40f3-9518-95d1d352bdb2",
                "user_id": 1,
                "agent_id": 1,
                "title": "채팅 092ff3a4...",
                "status": "active",
                "channel_metadata": {
                    "agent_code": "caia",
                    "first_question": "LG전자의 최신 스마트폰 기술에 대해 알려주세요",
                },
                "last_message_at": "2024-01-15T10:35:00Z",
                "message_count": 4,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:35:00Z",
            }
        }


class ChatChannelWithMessagesResponse(ChatChannelResponse):
    """메시지가 포함된 채팅 채널 응답 모델"""

    messages: List[ChatMessageResponse] = Field(
        default_factory=list, description="채팅 메시지 목록"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": 45,
                "session_id": "092ff3a4-7a2d-40f3-9518-95d1d352bdb2",
                "user_id": 1,
                "agent_id": 1,
                "title": "채팅 092ff3a4...",
                "status": "active",
                "channel_metadata": {
                    "agent_code": "caia",
                    "first_question": "LG전자의 최신 스마트폰 기술에 대해 알려주세요",
                },
                "last_message_at": "2024-01-15T10:35:00Z",
                "message_count": 4,
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:35:00Z",
                "messages": [
                    {
                        "id": 123,
                        "channel_id": 45,
                        "agent_id": 1,
                        "message_type": "user",
                        "content": "LG전자의 최신 스마트폰 기술에 대해 알려주세요",
                        "message_metadata": {
                            "total_token": 15,
                            "model": ["user_input"],
                        },
                        "parent_message_id": None,
                        "is_deleted": False,
                        "created_at": "2024-01-15T10:30:00Z",
                        "updated_at": "2024-01-15T10:30:00Z",
                    }
                ],
            }
        }


class ChatChannelListResponse(BaseModel):
    """채팅 채널 목록 응답 모델"""

    channels: List[ChatChannelResponse] = Field(..., description="채팅 채널 목록")
    total_count: int = Field(..., description="전체 채널 수")
    page: int = Field(..., description="현재 페이지")
    page_size: int = Field(..., description="페이지 크기")

    class Config:
        json_schema_extra = {
            "example": {
                "channels": [
                    {
                        "id": 45,
                        "session_id": "092ff3a4-7a2d-40f3-9518-95d1d352bdb2",
                        "user_id": 1,
                        "agent_id": 1,
                        "title": "채팅 092ff3a4...",
                        "status": "active",
                        "channel_metadata": {"agent_code": "caia"},
                        "last_message_at": "2024-01-15T10:35:00Z",
                        "message_count": 4,
                        "created_at": "2024-01-15T10:30:00Z",
                        "updated_at": "2024-01-15T10:35:00Z",
                    }
                ],
                "total_count": 1,
                "page": 1,
                "page_size": 20,
            }
        }
