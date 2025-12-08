"""
SQLAlchemy 모델 정의

기존 MySQL 스키마를 기반으로 한 SQLAlchemy 모델들
역할별로 분리된 모델들을 통합하여 import
"""

# Domain-specific models
from .agent import Agent, AgentLLMConfig

# Base and common components
from .base import Base
from .chat import ChatChannel, ChatChannelStatus, ChatMessage, MessageType
from .memory import Memory, MemorySource, MemoryType
from .user import User, UserAgentMembership
from .task import Task
from .api_key import APIKey
from .api_key_agent import APIKeyAgentPermission

# Re-export all models for backward compatibility
__all__ = [
    "Base",
    "Agent",
    "AgentLLMConfig",
    "User",
    "UserAgentMembership",
    "Memory",
    "MemoryType",
    "MemorySource",
    "ChatChannel",
    "ChatChannelStatus",
    "ChatMessage",
    "MessageType",
    "Task",
    "APIKey",
    "APIKeyAgentPermission",
]
