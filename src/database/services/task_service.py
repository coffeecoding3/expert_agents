"""
Task 관련 데이터베이스 서비스

법령 개정 분석 작업 이력 관리
"""

import uuid
from datetime import datetime
from logging import getLogger
from typing import Any, Dict, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Task
from .base_orm_service import ORMService

logger = getLogger("database")


class TaskService(ORMService[Task]):
    """작업 이력 서비스"""

    def __init__(self):
        super().__init__(Task)

    def create_task(
        self,
        db: Session,
        openapi_log_id: Optional[str] = None,
        old_and_new_no: Optional[str] = None,
        law_nm: str = "",
        request_data: Optional[Dict[str, Any]] = None,
        status: str = "pending",
    ) -> Optional[Task]:
        """
        작업 이력을 생성합니다.

        Args:
            db: 데이터베이스 세션
            openapi_log_id: OpenAPI 로그 ID
            old_and_new_no: 개정 전후 번호
            law_nm: 법령명
            request_data: 원본 요청 데이터
            status: 상태 (pending, processing, completed, failed)

        Returns:
            Task: 생성된 작업 이력
        """
        try:
            task = Task(
                task_id=str(uuid.uuid4()),
                openapi_log_id=openapi_log_id,
                old_and_new_no=old_and_new_no,
                law_nm=law_nm,
                request_data=request_data,
                status=status,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            logger.info(f"[TASK_SERVICE] 작업 이력 생성 완료: task_id={task.task_id}")
            return task
        except SQLAlchemyError as e:
            logger.error(f"[TASK_SERVICE] 작업 이력 생성 실패: {e}")
            db.rollback()
            return None

    def get_by_task_id(self, db: Session, task_id: str) -> Optional[Task]:
        """task_id로 작업 이력 조회"""
        try:
            return db.query(Task).filter(Task.task_id == task_id).first()
        except SQLAlchemyError as e:
            logger.error(f"[TASK_SERVICE] task_id로 작업 이력 조회 실패: {e}")
            return None

    def get_by_openapi_log_id(self, db: Session, openapi_log_id: str) -> Optional[Task]:
        """openapi_log_id로 작업 이력 조회"""
        try:
            return db.query(Task).filter(Task.openapi_log_id == openapi_log_id).first()
        except SQLAlchemyError as e:
            logger.error(f"[TASK_SERVICE] openapi_log_id로 작업 이력 조회 실패: {e}")
            return None

    def get_latest_completed_by_law_nm(
        self, db: Session, law_nm: str
    ) -> Optional[Task]:
        """law_nm으로 가장 최근 완료된 작업 이력 조회"""
        try:
            return (
                db.query(Task)
                .filter(Task.law_nm == law_nm, Task.status == "completed")
                .order_by(Task.created_at.desc())
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"[TASK_SERVICE] law_nm으로 작업 이력 조회 실패: {e}")
            return None

    def update_task(
        self,
        db: Session,
        task_id: str,
        corporate_knowledge: Optional[Dict[str, Any]] = None,
        advice_content: Optional[str] = None,
        advice_parsed: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        error_message: Optional[str] = None,
        processing_time_ms: Optional[int] = None,
        llm_model: Optional[str] = None,
        llm_usage: Optional[Dict[str, Any]] = None,
    ) -> Optional[Task]:
        """
        작업 이력을 업데이트합니다.

        Args:
            db: 데이터베이스 세션
            task_id: 작업 ID
            corporate_knowledge: MCP 검색 결과
            advice_content: LLM 생성 조언 원문
            advice_parsed: 파싱된 조언 데이터
            status: 상태
            error_message: 오류 메시지
            processing_time_ms: 처리 시간 (밀리초)
            llm_model: 사용된 LLM 모델
            llm_usage: LLM 토큰 사용량

        Returns:
            Task: 업데이트된 작업 이력
        """
        try:
            task = self.get_by_task_id(db, task_id)
            if not task:
                logger.warning(
                    f"[TASK_SERVICE] 작업 이력을 찾을 수 없습니다: task_id={task_id}"
                )
                return None

            if corporate_knowledge is not None:
                task.corporate_knowledge = corporate_knowledge
            if advice_content is not None:
                task.advice_content = advice_content
            if advice_parsed is not None:
                task.advice_parsed = advice_parsed
            if status is not None:
                task.status = status
            if error_message is not None:
                task.error_message = error_message
            if processing_time_ms is not None:
                task.processing_time_ms = processing_time_ms
            if llm_model is not None:
                task.llm_model = llm_model
            if llm_usage is not None:
                task.llm_usage = llm_usage

            db.commit()
            db.refresh(task)
            logger.info(f"[TASK_SERVICE] 작업 이력 업데이트 완료: task_id={task_id}")
            return task
        except SQLAlchemyError as e:
            logger.error(f"[TASK_SERVICE] 작업 이력 업데이트 실패: {e}")
            db.rollback()
            return None


# 전역 서비스 인스턴스
task_service = TaskService()
