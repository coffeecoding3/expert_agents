"""
사용자 관련 데이터베이스 서비스

User 관련 서비스들
"""

from logging import getLogger
from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import User
from .base_orm_service import ORMService

logger = getLogger("database")


class UserService(ORMService[User]):
    """사용자 서비스"""

    def __init__(self):
        super().__init__(User)

    def get_by_user_id(self, db: Session, user_id: str) -> Optional[User]:
        """사용자 ID로 조회"""
        try:
            return db.query(User).filter(User.user_id == user_id).first()
        except SQLAlchemyError as e:
            logger.error(f"사용자 ID 조회 실패: {e}")
            return None

    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        """사용자명으로 조회"""
        try:
            return db.query(User).filter(User.username == username).first()
        except SQLAlchemyError as e:
            logger.error(f"사용자명 조회 실패: {e}")
            return None

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """이메일로 조회"""
        try:
            return db.query(User).filter(User.email == email).first()
        except SQLAlchemyError as e:
            logger.error(f"이메일 조회 실패: {e}")
            return None

    def get_active_users(self, db: Session) -> List[User]:
        """활성 사용자 목록 조회"""
        try:
            return db.query(User).filter(User.use_yn == True).all()
        except SQLAlchemyError as e:
            logger.error(f"활성 사용자 조회 실패: {e}")
            return []


# 서비스 인스턴스
user_service = UserService()
