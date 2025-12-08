"""
Chat-related SQLAlchemy models and enums
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class ChatChannelStatus(str, Enum):
    """채팅방 상태 열거형"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class MessageType(str, Enum):
    """메시지 타입 열거형"""

    USER = "user"
    SYSTEM = "system"
    TOOL = "tool"


class ChatChannel(Base):
    """채팅방(채널) 테이블"""

    __tablename__ = "chat_channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    agent_id = Column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    title = Column(String(500), nullable=True)  # 채팅방 제목
    status = Column(SQLEnum(ChatChannelStatus), default=ChatChannelStatus.ACTIVE)
    channel_metadata = Column(JSON, nullable=True)  # 추가 메타데이터
    last_message_at = Column(DateTime, nullable=True)  # 마지막 메시지 시간
    message_count = Column(Integer, default=0)  # 메시지 수
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # 관계
    user = relationship("User", back_populates="chat_channels")
    agent = relationship("Agent", back_populates="chat_channels")
    messages = relationship(
        "ChatMessage", back_populates="channel", cascade="all, delete-orphan"
    )

    # 인덱스
    __table_args__ = (
        Index("idx_chat_channels_user_agent", "user_id", "agent_id"),
        Index("idx_chat_channels_status", "status"),
        Index("idx_chat_channels_last_message", "last_message_at"),
    )


class ChatMessage(Base):
    """채팅 메시지 테이블"""

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    channel_id = Column(
        Integer, ForeignKey("chat_channels.id", ondelete="CASCADE"), nullable=False
    )
    agent_id = Column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )  # 에이전트 연결
    message_type = Column(
        String(100), nullable=False
    )  # USER, SYSTEM, TOOL 또는 에이전트 이름
    content = Column(Text, nullable=False)  # 메시지 내용
    message_metadata = Column(
        JSON, nullable=True
    )  # 추가 메타데이터 (total_token, model만)
    parent_message_id = Column(
        Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True
    )  # 답변 관계
    is_deleted = Column(Boolean, default=False)  # 삭제 여부
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # 관계
    channel = relationship("ChatChannel", back_populates="messages")
    agent = relationship("Agent", back_populates="chat_messages")
    parent_message = relationship(
        "ChatMessage", remote_side=[id], back_populates="replies"
    )
    replies = relationship(
        "ChatMessage", back_populates="parent_message", cascade="all, delete-orphan"
    )

    # 인덱스
    __table_args__ = (
        Index("idx_chat_messages_channel", "channel_id"),
        Index("idx_chat_messages_agent", "agent_id"),
        Index("idx_chat_messages_type", "message_type"),
        Index("idx_chat_messages_created", "created_at"),
        Index("idx_chat_messages_parent", "parent_message_id"),
    )
