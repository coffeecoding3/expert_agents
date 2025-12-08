"""
API Key - Agent 권한 관리 모델

API Key가 접근할 수 있는 Agent를 정의하는 Many-to-Many 관계 테이블
"""

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from .base import Base


class APIKeyAgentPermission(Base):
    """API Key - Agent 권한 테이블 (Many-to-Many)"""

    __tablename__ = "api_key_agent_permissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key_id = Column(
        Integer,
        ForeignKey("api_keys.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        Integer,
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 관계
    api_key = relationship("APIKey", back_populates="agent_permissions")
    agent = relationship("Agent", back_populates="api_key_permissions")

    # 제약 조건
    __table_args__ = (
        UniqueConstraint("api_key_id", "agent_id", name="uq_api_key_agent"),
        Index("idx_api_key_agent_key", "api_key_id"),
        Index("idx_api_key_agent_agent", "agent_id"),
    )
