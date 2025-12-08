"""
Memory-related SQLAlchemy models and enums
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class MemoryType(str, Enum):
    """메모리 타입 열거형"""

    LTM = "long_term_memory"
    STM = "short_term_memory"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemorySource(str, Enum):
    """메모리 소스 열거형"""

    FACT = "FACT"
    INFERRED = "INFERRED"


class Memory(Base):
    """메모리 테이블"""

    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content = Column(Text, nullable=False)
    memory_type = Column(
        SQLEnum(MemoryType, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=MemoryType.EPISODIC
    )
    importance = Column(Float, default=1.0)
    category = Column(String(64), nullable=False, default="")
    source = Column(
        SQLEnum(MemorySource, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=MemorySource.INFERRED
    )
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    accessed_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # 관계
    user = relationship("User", back_populates="memories")
    agent = relationship("Agent", back_populates="memories")

    # 유니크 제약조건
    __table_args__ = (
        UniqueConstraint(
            "user_id", "agent_id", "memory_type", "category", name="uniq_owner_type_cat"
        ),
    )
