"""
SQLAlchemy ORM 기반 공통 데이터베이스 서비스

모든 ORM 서비스의 기본 클래스
"""

from logging import getLogger
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import and_, asc, desc, func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from ..models import Base

logger = getLogger("database")

T = TypeVar("T", bound=Base)


class ORMService(Generic[T]):
    """SQLAlchemy ORM 기반 공통 데이터베이스 서비스"""

    def __init__(self, model_class: Type[T]):
        self.model_class = model_class

    def create(self, db: Session, **kwargs) -> Optional[T]:
        """새 레코드 생성"""
        try:
            instance = self.model_class(**kwargs)
            db.add(instance)
            db.commit()
            db.refresh(instance)
            # 복합 기본키인 경우 ID 로깅 스킵
            if hasattr(instance, "id"):
                logger.info(
                    f"{self.model_class.__name__} 레코드가 생성되었습니다: {instance.id}"
                )
            else:
                logger.info(f"{self.model_class.__name__} 레코드가 생성되었습니다")
            return instance
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"{self.model_class.__name__} 생성 실패: {e}")
            return None

    def get_by_id(self, db: Session, id: int) -> Optional[T]:
        """ID로 레코드 조회"""
        try:
            return db.query(self.model_class).filter(self.model_class.id == id).first()
        except SQLAlchemyError as e:
            logger.error(f"{self.model_class.__name__} 조회 실패: {e}")
            return None

    def get_all(self, db: Session, skip: int = 0, limit: int = 100) -> List[T]:
        """모든 레코드 조회 (페이징)"""
        try:
            return db.query(self.model_class).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            logger.error(f"{self.model_class.__name__} 목록 조회 실패: {e}")
            return []

    def update(self, db: Session, id: int, **kwargs) -> Optional[T]:
        """레코드 업데이트"""
        try:
            instance = (
                db.query(self.model_class).filter(self.model_class.id == id).first()
            )
            if not instance:
                return None

            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)

            db.commit()
            db.refresh(instance)
            logger.info(
                f"{self.model_class.__name__} 레코드가 업데이트되었습니다: {id}"
            )
            return instance
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"{self.model_class.__name__} 업데이트 실패: {e}")
            return None

    def delete(self, db: Session, id: int) -> bool:
        """레코드 삭제"""
        try:
            instance = (
                db.query(self.model_class).filter(self.model_class.id == id).first()
            )
            if not instance:
                return False

            db.delete(instance)
            db.commit()
            logger.debug(f"{self.model_class.__name__} 레코드가 삭제되었습니다: {id}")
            return True
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"{self.model_class.__name__} 삭제 실패: {e}")
            return False

    def filter_by(self, db: Session, **filters) -> List[T]:
        """조건으로 레코드 필터링"""
        try:
            query = db.query(self.model_class)
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            return query.all()
        except SQLAlchemyError as e:
            logger.error(f"{self.model_class.__name__} 필터링 실패: {e}")
            return []

    def count(self, db: Session, **filters) -> int:
        """조건에 맞는 레코드 수 조회"""
        try:
            query = db.query(self.model_class)
            for key, value in filters.items():
                if hasattr(self.model_class, key):
                    query = query.filter(getattr(self.model_class, key) == value)
            return query.count()
        except SQLAlchemyError as e:
            logger.error(f"{self.model_class.__name__} 카운트 실패: {e}")
            return 0
