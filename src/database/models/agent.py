"""
Agent-related SQLAlchemy models
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class Agent(Base):
    """에이전트 테이블"""

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    code = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    description_en = Column(Text)
    tag = Column(String(50), nullable=True)  # 에이전트별 태그 (예: "NEW", "COM" 등)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # 관계
    user_memberships = relationship("UserAgentMembership", back_populates="agent")
    memories = relationship("Memory", back_populates="agent")
    chat_channels = relationship("ChatChannel", back_populates="agent")
    chat_messages = relationship("ChatMessage", back_populates="agent")
    llm_config = relationship("AgentLLMConfig", back_populates="agent", uselist=False)
    api_key_permissions = relationship(
        "APIKeyAgentPermission", back_populates="agent", cascade="all, delete-orphan"
    )


class AgentLLMConfig(Base):
    """에이전트별 LLM 설정 테이블"""

    __tablename__ = "agent_llm_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    provider = Column(String(50), nullable=True)  # "openai", "anthropic" 등
    model = Column(String(100), nullable=True)  # 모델 이름
    temperature = Column(Float, nullable=True)
    max_tokens = Column(Integer, nullable=True)
    config_json = Column(
        JSON, nullable=True
    )  # provider별 추가 설정 (api_key, base_url, api_version, deployment 등)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # 관계
    agent = relationship("Agent", back_populates="llm_config")
