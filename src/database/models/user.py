"""
User-related SQLAlchemy models
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .base import Base


class User(Base):
    """사용자 테이블"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creation_user_id = Column(String(100), default="system")
    creation_date = Column(DateTime, default=func.current_timestamp())
    last_update_user_id = Column(String(100), default="system")
    last_update_date = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )
    user_id = Column(String(100), unique=True, nullable=False)
    username = Column(String(100), nullable=False)
    username_eng = Column(String(100))
    email = Column(String(255))
    is_admin = Column(String(20), default="user")
    use_yn = Column(Boolean, default=True)
    nationality = Column(String(50))
    division = Column(String(100))
    organ = Column(String(100))
    organ_name = Column(String(200))
    location = Column(String(200))
    division1_nm = Column(String(200))
    division2_nm = Column(String(200))
    approval_status = Column(String(50), default="pending")
    authority_group_code = Column(String(50))
    sabun = Column(String(50))
    # 추가 HR 데이터 컬럼들
    name = Column(String(100))
    jikwi = Column(String(100))
    sf_user_id = Column(String(100))
    employee_category = Column(String(100))
    job_name = Column(String(200))
    jikchek_name = Column(String(200))
    jikwi_name = Column(String(200))

    # 관계
    agent_memberships = relationship("UserAgentMembership", back_populates="user")
    memories = relationship("Memory", back_populates="user")
    chat_channels = relationship("ChatChannel", back_populates="user")


class UserAgentMembership(Base):
    """사용자-에이전트 멤버십 테이블"""

    __tablename__ = "user_agent_memberships"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    agent_id = Column(
        Integer, ForeignKey("agents.id", ondelete="CASCADE"), primary_key=True
    )
    role = Column(String(32), default="member")
    enabled = Column(Boolean, default=True)
    expires_at = Column(DateTime)

    # 관계
    user = relationship("User", back_populates="agent_memberships")
    agent = relationship("Agent", back_populates="user_memberships")
