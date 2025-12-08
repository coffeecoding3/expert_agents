"""
Chat Models

채팅 관련 데이터 모델
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """메시지 역할"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class ChatMessage(BaseModel):
    """채팅 메시지"""

    role: MessageRole
    content: str
    name: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "role": "user",
                "content": "안녕하세요!",
                "timestamp": "2024-01-01T00:00:00",
                "metadata": {},
            }
        }


class ChatResponse(BaseModel):
    """채팅 응답"""

    content: str
    model_name: str
    usage: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    response_time: Optional[float] = None  # 응답 시간 (초 단위)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "content": "안녕하세요! 무엇을 도와드릴까요?",
                "model_name": "gpt-4",
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
                "finish_reason": "stop",
                "timestamp": "2024-01-01T00:00:00",
            }
        }


class StreamingChatResponse(BaseModel):
    """스트리밍 채팅 응답"""

    content: str
    model_name: str
    is_complete: bool = False
    usage: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    response_time: Optional[float] = None  # 응답 시간 (초 단위)
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "content": "안녕하세요!",
                "model_name": "gpt-4",
                "is_complete": False,
                "timestamp": "2024-01-01T00:00:00",
            }
        }


class ChatRequest(BaseModel):
    """채팅 요청"""

    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "messages": [{"role": "user", "content": "안녕하세요!"}],
                "model": "gpt-4",
                "temperature": 0.7,
                "stream": False,
            }
        }
