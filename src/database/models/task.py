"""
Task-related SQLAlchemy models

법령 개정 분석 작업 이력을 저장하는 테이블
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    JSON,
    String,
    Text,
    Index,
)
from sqlalchemy.dialects.mysql import CHAR
from sqlalchemy.sql import func

from .base import Base


class Task(Base):
    """법령 개정 분석 작업 이력 테이블"""

    __tablename__ = "lexai_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        CHAR(36),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )  # UUID 형식의 작업 ID
    openapi_log_id = Column(String(255), nullable=True, index=True)  # OpenAPI 로그 ID
    old_and_new_no = Column(String(255), nullable=True)  # 개정 전후 번호
    law_nm = Column(String(500), nullable=False, index=True)  # 법령명

    # 요청 데이터
    request_data = Column(JSON, nullable=True)  # 원본 요청 데이터 (LexAIRequest)

    # 처리 결과
    corporate_knowledge = Column(JSON, nullable=True)  # MCP 검색 결과
    advice_content = Column(Text, nullable=True)  # LLM 생성 조언 원문
    advice_parsed = Column(
        JSON, nullable=True
    )  # 파싱된 조언 데이터 (RegulationChangeResponse)

    # 메타데이터
    status = Column(
        String(50), default="pending", index=True
    )  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)  # 오류 메시지
    processing_time_ms = Column(Integer, nullable=True)  # 처리 시간 (밀리초)

    # LLM 메타데이터
    llm_model = Column(String(100), nullable=True)  # 사용된 LLM 모델
    llm_usage = Column(JSON, nullable=True)  # LLM 토큰 사용량

    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(
        DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp()
    )

    # 인덱스
    __table_args__ = (
        Index("idx_lexai_task_law_nm", "law_nm"),
        Index("idx_lexai_task_status", "status"),
        Index("idx_lexai_task_created", "created_at"),
        Index("idx_lexai_task_openapi_log_id", "openapi_log_id"),
    )
