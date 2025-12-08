"""
API Key SQLAlchemy model

LexAI API 인증을 위한 API Key 관리 테이블
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Boolean,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class APIKey(Base):
    """API Key 관리 테이블"""

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_hash = Column(
        String(255), unique=True, nullable=False, index=True
    )  # 해시된 API Key (SHA-256)
    name = Column(String(255), nullable=True)  # 키 이름/설명
    is_active = Column(Boolean, default=True, nullable=False, index=True)  # 활성화 여부
    expires_at = Column(
        DateTime, nullable=True, index=True
    )  # 만료일 (None이면 만료 없음)
    last_used_at = Column(DateTime, nullable=True)  # 마지막 사용 시간
    created_at = Column(DateTime, default=func.current_timestamp(), nullable=False)
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # 관계
    agent_permissions = relationship(
        "APIKeyAgentPermission", back_populates="api_key", cascade="all, delete-orphan"
    )

    # 인덱스
    __table_args__ = (
        Index("idx_api_keys_hash", "key_hash"),
        Index("idx_api_keys_active", "is_active"),
        Index("idx_api_keys_expires", "expires_at"),
    )

    def is_expired(self) -> bool:
        """만료 여부 확인"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """유효성 확인 (활성화 여부 + 만료 여부)"""
        return self.is_active and not self.is_expired()

    def has_agent_permission(self, agent_code: str) -> bool:
        """
        특정 Agent에 대한 권한이 있는지 확인

        Args:
            agent_code: Agent 코드 (예: "lexai", "caia")

        Returns:
            bool: 권한이 있으면 True
        """
        # agent_permissions가 None이거나 빈 리스트인 경우 모든 agent 접근 가능 (하위 호환성)
        if not self.agent_permissions or len(self.agent_permissions) == 0:
            return True

        # agent_permissions가 있으면 해당 agent_code에 대한 권한이 있는지 확인
        # 대소문자 무시 비교 (agent.code가 "LEXAI"로 저장되어 있을 수 있음)
        agent_code_lower = agent_code.lower()
        for perm in self.agent_permissions:
            # agent 관계가 로드되지 않은 경우를 대비해 확인
            if perm.agent is None:
                # agent가 None이면 건너뛰기 (관계가 제대로 설정되지 않았을 수 있음)
                continue
            
            # agent.code와 대소문자 무시 비교
            if perm.agent.code.lower() == agent_code_lower:
                return True
        
        # agent_permissions가 있지만 해당 agent_code에 대한 권한이 없는 경우
        return False
