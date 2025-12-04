"""
User Authentication Service

사용자 인증 및 관리 서비스 - 리팩토링된 버전
"""

# CAIA User Authorizer 임포트
import sys
import urllib.parse
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.append(str(Path(__file__).parent.parent.parent))
from src.agents.components.common.user_authorizer import get_authorizer
from src.apps.api.security.authorization_service import authorization_service
from src.apps.api.security.crypto import SSOAuthenticationException, decrypt_aes256
from src.apps.api.security.sso_parser import sso_parser
from src.apps.api.user.user_manager import user_manager
from src.schemas.user_schemas import user_info_to_dict

logger = getLogger("user_service")


class UserAuthService:
    """사용자 인증 서비스 - 리팩토링된 버전"""

    def __init__(self):
        self.logger = logger
        self.test_mode = False  # 실제 데이터베이스 사용

    def get_user_from_cookie(
        self,
        cookie_value: str,
        agent_filter: str = "lge_caia",
        agent_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        쿠키 값에서 사용자 정보 추출 (엘지니 SSO 방식)

        Args:
            cookie_value: ssolgenet_exa 쿠키 값
            agent_filter: 권한 필터 (기본값: lge_caia)
            agent_code: 에이전트 코드 (agent_filter에서 추출하거나 직접 지정)

        Returns:
            사용자 정보 딕셔너리 또는 None
        """
        try:
            # 1. 쿠키 유효성 검사
            if not cookie_value:
                self.logger.warning("[USER_SERVICE] ssolgenet_exa 쿠키가 없습니다.")
                return None

            # 2. 사용자 ID 추출
            user_id = self._extract_user_id_from_cookie(cookie_value)
            if not user_id:
                return None

            # 3. 테스트 모드 처리
            if self.test_mode:
                return self._handle_test_mode(user_id)

            # 4. agent_code 추출 (agent_filter에서 추출하거나 직접 지정)
            if not agent_code:
                # agent_filter에서 agent_code 추출 (예: "lge_caia" -> "caia")
                if agent_filter.startswith("lge_"):
                    agent_code = agent_filter[4:].lower()
                else:
                    # 기본값으로 caia 사용
                    agent_code = "caia"
                    self.logger.warning(
                        f"[USER_SERVICE] agent_filter에서 agent_code를 추출할 수 없어 기본값 'caia' 사용: {agent_filter}"
                    )

            # 5. 실제 사용자 정보 조회 및 검증
            user_info = self._get_and_validate_user_info(
                user_id, agent_filter, agent_code
            )
            if not user_info:
                return None

            # 5. 사용자 정보를 딕셔너리로 변환
            user_dict = user_info_to_dict(user_info)

            # 6. 데이터베이스 저장 및 메모리 업데이트
            self._save_user_data_and_memory(user_dict)

            return user_dict

        except Exception as e:
            self.logger.error(f"[USER_SERVICE] 사용자 쿠키에서 정보 추출 실패: {e}")
            return None

    def _extract_user_id_from_cookie(self, cookie_value: str) -> Optional[str]:
        """쿠키에서 사용자 ID 추출"""
        try:
            sso_info = urllib.parse.unquote(cookie_value)
            tokens = sso_info.split("id=")

            if len(tokens) < 2:
                self.logger.warning("[USER_SERVICE] 잘못된 SSO 쿠키 형식입니다.")
                return None

            param_id = tokens[1]
            if not param_id:
                self.logger.warning(
                    "[USER_SERVICE] SSO 쿠키에서 ID를 찾을 수 없습니다."
                )
                return None

            # AES256 복호화로 사용자 ID 추출
            try:
                user_id = decrypt_aes256(param_id)
                self.logger.debug(f"[USER_SERVICE] SSO 복호화 성공: {user_id}")
                return user_id
            except SSOAuthenticationException as e:
                self.logger.error(f"[USER_SERVICE] SSO 복호화 실패: {e.message}")
                return None

        except Exception as e:
            self.logger.error(f"[USER_SERVICE] 사용자 ID 추출 실패: {e}")
            return None

    def _get_and_validate_user_info(
        self, user_id: str, agent_filter: str, agent_code: str = "caia"
    ) -> Optional[Any]:
        """사용자 정보 조회 및 검증"""
        # User Authorizer를 사용하여 실제 사용자 정보 조회
        authorizer = get_authorizer()
        user_info = authorizer.get_user_info(user_id, agent_code)

        if not user_info:
            self.logger.warning(
                f"[USER_SERVICE] 데이터베이스에서 사용자를 찾을 수 없습니다: {user_id}"
            )
            return None

        # 권한 검증
        agent_authority = authorizer.check_agent_authority(user_id, agent_code)
        if not agent_authority:
            self.logger.debug(
                f"[USER_SERVICE] 사용자 {user_id}에게 {agent_code.upper()} 권한이 없습니다."
            )
            return None

        # 서비스 사용 가능 여부 검증
        service_use_yn = authorization_service.validate_user_authorities(
            user_info.user_authorities, agent_filter
        )
        if not service_use_yn:
            self.logger.warning(
                f"[USER_SERVICE] 사용자 {user_id}에게 {agent_filter} 권한이 없습니다."
            )
            return None

        return user_info

    def _save_user_data_and_memory(self, user_dict: Dict[str, Any]) -> None:
        """사용자 데이터 저장 및 메모리 업데이트"""
        # main 데이터베이스에 사용자 정보 저장/업데이트
        db_user_id = user_manager.save_or_update_user(user_dict)
        if db_user_id:
            # 데이터베이스 사용자 ID 추가
            user_dict["db_user_id"] = db_user_id
            self.logger.debug(f"사용자 정보 저장 완료: DB ID {db_user_id}")

            # SSO 로그인 시 처음 로그인한 사용자에게 모든 agent에 대한 membership 추가
            try:
                self._ensure_all_agents_membership(db_user_id)
            except Exception as e:
                self.logger.error(f"모든 agent에 대한 membership 추가 중 오류: {e}")
            
            # 인사정보를 semantic 메모리에 비동기로 저장 (DB 저장 성공한 경우에만)
            try:
                user_manager.update_personnel_memory_async(db_user_id, user_dict)
            except Exception as e:
                self.logger.error(f"인사정보 메모리 비동기 저장 시작 중 오류: {e}")
        else:
            # 데이터베이스 저장 실패 시 메모리 업데이트를 시도하지 않음
            # (외래키 제약조건 위반을 방지하기 위해)
            self.logger.warning(
                "사용자 정보 저장 실패, 메모리 업데이트를 건너뜁니다. "
                "DB에 사용자가 없으면 메모리 저장 시 외래키 제약조건 위반이 발생합니다."
            )

    def validate_user_session(self, user_info: Dict[str, Any]) -> bool:
        """
        사용자 세션 유효성 검증

        Args:
            user_info: 사용자 정보

        Returns:
            세션이 유효한지 여부
        """
        return authorization_service.validate_user_session(user_info)

    def _ensure_all_agents_membership(self, db_user_id: int) -> None:
        """SSO 로그인 시 처음 로그인한 사용자에게 모든 agent에 대한 membership 추가"""
        try:
            from src.utils.db_utils import get_db_session
            from src.database.services.agent_services import (
                agent_service,
                membership_service,
            )

            # context manager를 사용하여 세션 자동 정리
            with get_db_session() as db:
                # 사용자의 기존 멤버십 확인
                existing_memberships = membership_service.get_user_agents(
                    db, db_user_id
                )

                # 이미 멤버십이 있으면 스킵 (처음 로그인한 사용자가 아님)
                if existing_memberships:
                    self.logger.debug(
                        f"사용자 {db_user_id}는 이미 {len(existing_memberships)}개의 멤버십이 있습니다. 스킵합니다."
                    )
                    return

                # 모든 활성 agent 조회
                active_agents = agent_service.get_active_agents(db)
                if not active_agents:
                    self.logger.warning("활성 agent가 없습니다.")
                    return

                # 각 agent에 대해 멤버십 생성
                created_count = 0
                for agent in active_agents:
                    membership = membership_service.create_or_update_membership(
                        db=db,
                        user_id=db_user_id,
                        agent_id=agent.id,
                        role="member",
                        enabled=True,
                        expires_at=None,
                    )
                    if membership:
                        created_count += 1
                        self.logger.info(
                            f"사용자 {db_user_id}에게 agent {agent.code} (ID: {agent.id}) 멤버십 추가 완료"
                        )

                self.logger.info(
                    f"사용자 {db_user_id}에게 {created_count}개의 agent 멤버십이 추가되었습니다."
                )
        except Exception as e:
            self.logger.error(f"모든 agent에 대한 membership 추가 실패: {e}")
            raise

    def get_sso_id_from_user_id(self, user_id: int) -> Optional[str]:
        """
        데이터베이스 user_id(숫자)를 sso_id(문자열)로 변환

        Args:
            user_id: 데이터베이스의 user ID (숫자)

        Returns:
            sso_id (문자열) 또는 None
        """
        try:
            from src.utils.db_utils import get_db_session
            from src.database.models.user import User

            # context manager를 사용하여 세션 자동 정리
            with get_db_session() as db:
                user = db.query(User).filter(User.id == user_id).first()

                if user and user.user_id:
                    self.logger.info(
                        f"[USER_SERVICE] user_id {user_id} -> sso_id {user.user_id} 변환 성공"
                    )
                    return user.user_id
                else:
                    self.logger.warning(
                        f"[USER_SERVICE] user_id {user_id}에 해당하는 사용자를 찾을 수 없습니다."
                    )
                    return None

        except Exception as e:
            self.logger.error(f"[USER_SERVICE] user_id -> sso_id 변환 실패: {e}")
            return None

    def close(self):
        """리소스 정리"""
        try:
            user_manager.close()
            self.logger.info("사용자 인증 서비스가 종료되었습니다.")
        except Exception as e:
            self.logger.error(f"사용자 인증 서비스 종료 중 오류: {e}")


# 전역 인스턴스
user_auth_service = UserAuthService()
