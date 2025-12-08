"""
에이전트 관련 데이터베이스 서비스

Agent, UserAgentMembership 관련 서비스들
"""

from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Agent, AgentLLMConfig, UserAgentMembership
from .base_orm_service import ORMService

logger = getLogger("database")


class AgentService(ORMService[Agent]):
    """에이전트 서비스"""

    def __init__(self):
        super().__init__(Agent)

    def get_by_code(self, db: Session, code: str) -> Optional[Agent]:
        """코드로 에이전트 조회"""
        try:
            return db.query(Agent).filter(Agent.code == code).first()
        except SQLAlchemyError as e:
            logger.error(f"에이전트 코드 조회 실패: {e}")
            return None

    def get_code_by_id(self, db: Session, agent_id: int) -> Optional[str]:
        """ID로 에이전트 코드 조회"""
        try:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            return agent.code if agent else None
        except SQLAlchemyError as e:
            logger.error(f"에이전트 코드 조회 실패 (agent_id={agent_id}): {e}")
            return None

    def get_name_by_id(self, db: Session, agent_id: int) -> Optional[str]:
        """ID로 에이전트 이름 조회"""
        try:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            return agent.name if agent else None
        except SQLAlchemyError as e:
            logger.error(f"에이전트 이름 조회 실패 (agent_id={agent_id}): {e}")
            return None

    def get_active_agents(self, db: Session) -> List[Agent]:
        """활성 에이전트 목록 조회"""
        try:
            return db.query(Agent).filter(Agent.is_active == True).all()
        except SQLAlchemyError as e:
            logger.error(f"활성 에이전트 조회 실패: {e}")
            return []


class UserAgentMembershipService(ORMService[UserAgentMembership]):
    """사용자-에이전트 멤버십 서비스"""

    def __init__(self):
        super().__init__(UserAgentMembership)

    def get_user_agents(self, db: Session, user_id: int) -> List[UserAgentMembership]:
        """사용자의 에이전트 멤버십 조회"""
        try:
            return (
                db.query(UserAgentMembership)
                .filter(
                    UserAgentMembership.user_id == user_id,
                    UserAgentMembership.enabled == True,
                )
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"사용자 에이전트 멤버십 조회 실패: {e}")
            return []

    def get_agent_users(self, db: Session, agent_id: int) -> List[UserAgentMembership]:
        """에이전트의 사용자 멤버십 조회"""
        try:
            return (
                db.query(UserAgentMembership)
                .filter(
                    UserAgentMembership.agent_id == agent_id,
                    UserAgentMembership.enabled == True,
                )
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"에이전트 사용자 멤버십 조회 실패: {e}")
            return []

    def has_access(self, db: Session, user_id: int, agent_id: int) -> bool:
        """사용자가 에이전트에 접근 권한이 있는지 확인"""
        try:
            membership = (
                db.query(UserAgentMembership)
                .filter(
                    UserAgentMembership.user_id == user_id,
                    UserAgentMembership.agent_id == agent_id,
                    UserAgentMembership.enabled == True,
                )
                .first()
            )
            return membership is not None
        except SQLAlchemyError as e:
            logger.error(f"접근 권한 확인 실패: {e}")
            return False

    def create_or_update_membership(
        self,
        db: Session,
        user_id: int,
        agent_id: int,
        role: str,
        enabled: bool,
        expires_at: Optional[datetime] = None,
    ) -> Optional[UserAgentMembership]:
        """사용자-에이전트 멤버십 생성 또는 업데이트"""
        try:
            # 기존 멤버십 확인
            existing_membership = (
                db.query(UserAgentMembership)
                .filter(
                    UserAgentMembership.user_id == user_id,
                    UserAgentMembership.agent_id == agent_id,
                )
                .first()
            )

            if existing_membership:
                # 기존 멤버십 업데이트
                existing_membership.role = role
                existing_membership.enabled = enabled
                existing_membership.expires_at = expires_at
                db.commit()
                db.refresh(existing_membership)
                logger.info(
                    f"멤버십 업데이트 완료: user_id={user_id}, agent_id={agent_id}, role={role}"
                )
                return existing_membership
            else:
                # 새 멤버십 생성
                # CAIA 에이전트는 멤버십 생성 시 enabled=False로 설정
                if agent_id == 1:
                    enabled = False
                else:
                    enabled = True
                new_membership = UserAgentMembership(
                    user_id=user_id,
                    agent_id=agent_id,
                    role=role,
                    enabled=enabled,
                    expires_at=expires_at,
                )
                db.add(new_membership)
                db.commit()
                db.refresh(new_membership)
                logger.info(
                    f"새 멤버십 생성 완료: user_id={user_id}, agent_id={agent_id}, role={role}"
                )
                return new_membership

        except SQLAlchemyError as e:
            logger.error(f"멤버십 생성/업데이트 실패: {e}")
            db.rollback()
            return None


class AgentMembershipService(ORMService[UserAgentMembership]):
    """에이전트 멤버십 서비스"""

    def __init__(self):
        super().__init__(UserAgentMembership)

    def get_agent_members(
        self, db: Session, agent_id: int
    ) -> List[UserAgentMembership]:
        """에이전트의 멤버들 조회"""
        try:
            return (
                db.query(UserAgentMembership)
                .filter(
                    UserAgentMembership.agent_id == agent_id,
                    UserAgentMembership.enabled == True,
                )
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"에이전트 멤버 조회 실패: {e}")
            return []

    def get_agent_member_count(self, db: Session, agent_id: int) -> int:
        """에이전트의 활성 멤버 수 조회"""
        try:
            return (
                db.query(UserAgentMembership)
                .filter(
                    UserAgentMembership.agent_id == agent_id,
                    UserAgentMembership.enabled == True,
                )
                .count()
            )
        except SQLAlchemyError as e:
            logger.error(f"에이전트 멤버 수 조회 실패: {e}")
            return 0

    def get_agents_by_user_count(self, db: Session, min_members: int = 1) -> List[int]:
        """최소 멤버 수 이상인 에이전트 ID 목록 조회"""
        try:
            result = (
                db.query(UserAgentMembership.agent_id)
                .filter(UserAgentMembership.enabled == True)
                .group_by(UserAgentMembership.agent_id)
                .having(func.count(UserAgentMembership.user_id) >= min_members)
                .all()
            )
            return [row[0] for row in result]
        except SQLAlchemyError as e:
            logger.error(f"멤버 수 기준 에이전트 조회 실패: {e}")
            return []

    def get_membership_stats(self, db: Session) -> Dict[str, int]:
        """멤버십 통계 조회"""
        try:
            total_memberships = db.query(UserAgentMembership).count()
            active_memberships = (
                db.query(UserAgentMembership)
                .filter(UserAgentMembership.enabled == True)
                .count()
            )
            unique_users = (
                db.query(UserAgentMembership.user_id)
                .filter(UserAgentMembership.enabled == True)
                .distinct()
                .count()
            )
            unique_agents = (
                db.query(UserAgentMembership.agent_id)
                .filter(UserAgentMembership.enabled == True)
                .distinct()
                .count()
            )

            return {
                "total_memberships": total_memberships,
                "active_memberships": active_memberships,
                "unique_users": unique_users,
                "unique_agents": unique_agents,
            }
        except SQLAlchemyError as e:
            logger.error(f"멤버십 통계 조회 실패: {e}")
            return {
                "total_memberships": 0,
                "active_memberships": 0,
                "unique_users": 0,
                "unique_agents": 0,
            }

    def bulk_disable_memberships(self, db: Session, user_ids: List[int]) -> int:
        """여러 사용자의 멤버십을 일괄 비활성화"""
        try:
            updated_count = (
                db.query(UserAgentMembership)
                .filter(UserAgentMembership.user_id.in_(user_ids))
                .update({"enabled": False}, synchronize_session=False)
            )
            db.commit()
            logger.info(f"{updated_count}개의 멤버십이 비활성화되었습니다.")
            return updated_count
        except SQLAlchemyError as e:
            logger.error(f"멤버십 일괄 비활성화 실패: {e}")
            db.rollback()
            return 0

    def bulk_enable_memberships(self, db: Session, user_ids: List[int]) -> int:
        """여러 사용자의 멤버십을 일괄 활성화"""
        try:
            updated_count = (
                db.query(UserAgentMembership)
                .filter(UserAgentMembership.user_id.in_(user_ids))
                .update({"enabled": True}, synchronize_session=False)
            )
            db.commit()
            logger.info(f"{updated_count}개의 멤버십이 활성화되었습니다.")
            return updated_count
        except SQLAlchemyError as e:
            logger.error(f"멤버십 일괄 활성화 실패: {e}")
            db.rollback()
            return 0


class AgentLLMConfigService(ORMService[AgentLLMConfig]):
    """에이전트 LLM 설정 서비스"""

    def __init__(self):
        super().__init__(AgentLLMConfig)

    def get_by_agent_id(self, db: Session, agent_id: int) -> Optional[AgentLLMConfig]:
        """agent_id로 LLM 설정 조회"""
        try:
            return (
                db.query(AgentLLMConfig)
                .filter(
                    AgentLLMConfig.agent_id == agent_id,
                    AgentLLMConfig.is_active == True,
                )
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"에이전트 LLM 설정 조회 실패 (agent_id={agent_id}): {e}")
            return None

    def get_by_agent_code(
        self, db: Session, agent_code: str
    ) -> Optional[AgentLLMConfig]:
        """agent_code로 LLM 설정 조회"""
        try:
            # 먼저 agent를 조회
            agent = agent_service.get_by_code(db, agent_code)
            if not agent:
                logger.warning(f"에이전트를 찾을 수 없습니다: {agent_code}")
                return None

            return self.get_by_agent_id(db, agent.id)
        except SQLAlchemyError as e:
            logger.error(f"에이전트 LLM 설정 조회 실패 (agent_code={agent_code}): {e}")
            return None

    def create_or_update(
        self,
        db: Session,
        agent_id: int,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        config_json: Optional[Dict] = None,
        is_active: bool = True,
    ) -> Optional[AgentLLMConfig]:
        """LLM 설정 생성 또는 업데이트"""
        try:
            # 기존 설정 확인
            existing_config = self.get_by_agent_id(db, agent_id)

            if existing_config:
                # 업데이트
                if provider is not None:
                    existing_config.provider = provider
                if model is not None:
                    existing_config.model = model
                if temperature is not None:
                    existing_config.temperature = temperature
                if max_tokens is not None:
                    existing_config.max_tokens = max_tokens
                if config_json is not None:
                    existing_config.config_json = config_json
                existing_config.is_active = is_active
                db.commit()
                db.refresh(existing_config)
                logger.info(f"에이전트 LLM 설정 업데이트 완료: agent_id={agent_id}")
                return existing_config
            else:
                # 생성
                new_config = AgentLLMConfig(
                    agent_id=agent_id,
                    provider=provider,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    config_json=config_json,
                    is_active=is_active,
                )
                db.add(new_config)
                db.commit()
                db.refresh(new_config)
                logger.info(f"에이전트 LLM 설정 생성 완료: agent_id={agent_id}")
                return new_config

        except SQLAlchemyError as e:
            logger.error(f"에이전트 LLM 설정 생성/업데이트 실패: {e}")
            db.rollback()
            return None


# 서비스 인스턴스들
agent_service = AgentService()
membership_service = UserAgentMembershipService()
agent_membership_service = AgentMembershipService()
agent_llm_config_service = AgentLLMConfigService()
