"""
API Key 관련 데이터베이스 서비스

LexAI API 인증을 위한 API Key 관리
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from logging import getLogger
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import APIKey
from .base_orm_service import ORMService

logger = getLogger("database")


class APIKeyService(ORMService[APIKey]):
    """API Key 서비스"""

    def __init__(self):
        super().__init__(APIKey)

    def _hash_key(self, key: str) -> str:
        """API Key를 SHA-256으로 해시"""
        return hashlib.sha256(key.encode()).hexdigest()

    def generate_key(self, length: int = 32) -> str:
        """
        새로운 API Key 생성

        Args:
            length: 키 길이 (기본 32자)

        Returns:
            str: 생성된 API Key (평문)
        """
        # URL-safe base64 인코딩된 랜덤 문자열 생성
        return secrets.token_urlsafe(length)

    def create_api_key(
        self,
        db: Session,
        name: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        agent_codes: Optional[list[str]] = None,
    ) -> tuple[Optional[str], Optional[APIKey]]:
        """
        새로운 API Key 생성 및 저장

        Args:
            db: 데이터베이스 세션
            name: 키 이름/설명
            expires_in_days: 만료일 (일 단위, None이면 만료 없음)
            agent_codes: 접근 가능한 Agent 코드 목록 (None이면 모든 agent 접근 가능)

        Returns:
            tuple: (평문 API Key, APIKey 객체)
        """
        try:
            # 평문 키 생성
            plain_key = self.generate_key()

            # 키 해시
            key_hash = self._hash_key(plain_key)

            # 만료일 계산
            expires_at = None
            if expires_in_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

            # DB에 저장
            api_key = APIKey(
                key_hash=key_hash,
                name=name,
                is_active=True,
                expires_at=expires_at,
            )

            db.add(api_key)
            db.flush()  # ID를 얻기 위해 flush

            # Agent 권한 추가
            if agent_codes:
                from ..models import Agent, APIKeyAgentPermission

                for agent_code in agent_codes:
                    agent = db.query(Agent).filter(Agent.code == agent_code).first()
                    if agent:
                        permission = APIKeyAgentPermission(
                            api_key_id=api_key.id, agent_id=agent.id
                        )
                        db.add(permission)
                    else:
                        logger.warning(
                            f"[API_KEY] Agent를 찾을 수 없습니다: {agent_code}"
                        )

            db.commit()
            db.refresh(api_key)

            logger.info(
                f"[API_KEY] API Key 생성 완료: name={name}, id={api_key.id}, agents={agent_codes or 'all'}"
            )

            return plain_key, api_key

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"[API_KEY] API Key 생성 실패: {e}")
            return None, None
        except Exception as e:
            db.rollback()
            logger.error(f"[API_KEY] API Key 생성 중 오류: {e}")
            return None, None

    def validate_key(self, db: Session, api_key: str) -> Optional[APIKey]:
        """
        API Key 유효성 검증

        Args:
            db: 데이터베이스 세션
            api_key: 검증할 API Key (평문)

        Returns:
            APIKey: 유효한 경우 APIKey 객체, 그렇지 않으면 None
        """
        try:
            # 키 해시
            key_hash = self._hash_key(api_key)

            # DB에서 조회 (관계도 함께 로드)
            from sqlalchemy.orm import joinedload
            from ..models import APIKeyAgentPermission

            api_key_obj = (
                db.query(APIKey)
                .options(
                    joinedload(APIKey.agent_permissions).joinedload(APIKeyAgentPermission.agent)
                )
                .filter(APIKey.key_hash == key_hash)
                .first()
            )

            if not api_key_obj:
                logger.warning("[API_KEY] API Key를 찾을 수 없습니다")
                return None

            # 유효성 검증
            if not api_key_obj.is_valid():
                logger.warning(
                    f"[API_KEY] API Key가 유효하지 않습니다: active={api_key_obj.is_active}, expired={api_key_obj.is_expired()}"
                )
                return None

            # 마지막 사용 시간 업데이트
            api_key_obj.last_used_at = datetime.utcnow()
            db.commit()

            return api_key_obj

        except SQLAlchemyError as e:
            logger.error(f"[API_KEY] API Key 검증 중 오류: {e}")
            return None
        except Exception as e:
            logger.error(f"[API_KEY] API Key 검증 중 예외: {e}")
            return None

    def deactivate_key(self, db: Session, key_id: int) -> bool:
        """
        API Key 비활성화

        Args:
            db: 데이터베이스 세션
            key_id: API Key ID

        Returns:
            bool: 성공 여부
        """
        try:
            api_key = db.query(APIKey).filter(APIKey.id == key_id).first()

            if not api_key:
                logger.warning(f"[API_KEY] API Key를 찾을 수 없습니다: id={key_id}")
                return False

            api_key.is_active = False
            db.commit()

            logger.info(f"[API_KEY] API Key 비활성화 완료: id={key_id}")
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"[API_KEY] API Key 비활성화 실패: {e}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"[API_KEY] API Key 비활성화 중 오류: {e}")
            return False

    def list_keys(
        self,
        db: Session,
        include_inactive: bool = False,
        agent_code: Optional[str] = None,
    ) -> list[APIKey]:
        """
        API Key 목록 조회

        Args:
            db: 데이터베이스 세션
            include_inactive: 비활성화된 키 포함 여부
            agent_code: 특정 Agent에 대한 권한이 있는 키만 조회 (None이면 전체)

        Returns:
            list[APIKey]: API Key 목록
        """
        try:
            from ..models import Agent, APIKeyAgentPermission

            query = db.query(APIKey)

            if not include_inactive:
                query = query.filter(APIKey.is_active == True)

            # Agent 필터링
            if agent_code:
                agent = db.query(Agent).filter(Agent.code == agent_code).first()
                if agent:
                    query = query.join(APIKeyAgentPermission).filter(
                        APIKeyAgentPermission.agent_id == agent.id
                    )

            return query.order_by(APIKey.created_at.desc()).all()

        except SQLAlchemyError as e:
            logger.error(f"[API_KEY] API Key 목록 조회 실패: {e}")
            return []
        except Exception as e:
            logger.error(f"[API_KEY] API Key 목록 조회 중 오류: {e}")
            return []

    def add_agent_permission(
        self, db: Session, api_key_id: int, agent_code: str
    ) -> bool:
        """
        API Key에 Agent 권한 추가

        Args:
            db: 데이터베이스 세션
            api_key_id: API Key ID
            agent_code: Agent 코드

        Returns:
            bool: 성공 여부
        """
        try:
            from ..models import Agent, APIKeyAgentPermission

            api_key = db.query(APIKey).filter(APIKey.id == api_key_id).first()
            if not api_key:
                logger.warning(f"[API_KEY] API Key를 찾을 수 없습니다: id={api_key_id}")
                return False

            agent = db.query(Agent).filter(Agent.code == agent_code).first()
            if not agent:
                logger.warning(f"[API_KEY] Agent를 찾을 수 없습니다: {agent_code}")
                return False

            # 이미 권한이 있는지 확인
            existing = (
                db.query(APIKeyAgentPermission)
                .filter(
                    APIKeyAgentPermission.api_key_id == api_key_id,
                    APIKeyAgentPermission.agent_id == agent.id,
                )
                .first()
            )

            if existing:
                logger.info(
                    f"[API_KEY] 이미 권한이 있습니다: api_key_id={api_key_id}, agent={agent_code}"
                )
                return True

            # 권한 추가
            permission = APIKeyAgentPermission(api_key_id=api_key_id, agent_id=agent.id)
            db.add(permission)
            db.commit()

            logger.info(
                f"[API_KEY] Agent 권한 추가 완료: api_key_id={api_key_id}, agent={agent_code}"
            )
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"[API_KEY] Agent 권한 추가 실패: {e}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"[API_KEY] Agent 권한 추가 중 오류: {e}")
            return False

    def remove_agent_permission(
        self, db: Session, api_key_id: int, agent_code: str
    ) -> bool:
        """
        API Key에서 Agent 권한 제거

        Args:
            db: 데이터베이스 세션
            api_key_id: API Key ID
            agent_code: Agent 코드

        Returns:
            bool: 성공 여부
        """
        try:
            from ..models import Agent, APIKeyAgentPermission

            agent = db.query(Agent).filter(Agent.code == agent_code).first()
            if not agent:
                logger.warning(f"[API_KEY] Agent를 찾을 수 없습니다: {agent_code}")
                return False

            permission = (
                db.query(APIKeyAgentPermission)
                .filter(
                    APIKeyAgentPermission.api_key_id == api_key_id,
                    APIKeyAgentPermission.agent_id == agent.id,
                )
                .first()
            )

            if not permission:
                logger.warning(
                    f"[API_KEY] 권한을 찾을 수 없습니다: api_key_id={api_key_id}, agent={agent_code}"
                )
                return False

            db.delete(permission)
            db.commit()

            logger.info(
                f"[API_KEY] Agent 권한 제거 완료: api_key_id={api_key_id}, agent={agent_code}"
            )
            return True

        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"[API_KEY] Agent 권한 제거 실패: {e}")
            return False
        except Exception as e:
            db.rollback()
            logger.error(f"[API_KEY] Agent 권한 제거 중 오류: {e}")
            return False


# 전역 인스턴스
api_key_service = APIKeyService()
