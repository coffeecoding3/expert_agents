"""
SQLAlchemy ORM 기반 데이터베이스 서비스

이 파일은 하위 호환성을 위해 유지되며,
실제 서비스들은 역할별로 분리된 파일들에서 import됩니다.

사용 권장사항:
- 새로운 코드에서는 개별 서비스 파일을 직접 import하세요
- 예: from .user_services import UserService
- 예: from .agent_services import AgentService
"""

from .agent_services import (
    AgentMembershipService,
    AgentService,
    UserAgentMembershipService,
    agent_membership_service,
    agent_service,
    membership_service,
)

# 하위 호환성을 위한 import
from .base_orm_service import ORMService
from .chat_services import (
    ChatChannelService,
    ChatMessageService,
    chat_channel_service,
    chat_message_service,
)
from .memory_service import MemoryService, memory_service
from .user_services import UserService, user_service

# 하위 호환성을 위해 모든 서비스와 인스턴스를 export
__all__ = [
    # Base service
    "ORMService",
    # Service classes
    "AgentService",
    "UserService",
    "UserAgentMembershipService",
    "AgentMembershipService",
    "MemoryService",
    "ChatChannelService",
    "ChatMessageService",
    # Service instances
    "agent_service",
    "user_service",
    "membership_service",
    "agent_membership_service",
    "memory_service",
    "chat_channel_service",
    "chat_message_service",
]
