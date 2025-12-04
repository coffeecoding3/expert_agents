"""
Authorization Service

사용자 권한 검증 및 인증을 담당하는 모듈
"""

from logging import getLogger
from typing import Any, Dict, List

logger = getLogger("authorization")


class AuthorizationService:
    """권한 검증 서비스"""

    def __init__(self):
        self.logger = logger

    def validate_user_authorities(
        self, user_authorities: List[Dict[str, Any]], agent_filter: str
    ) -> bool:
        """
        사용자 권한 검증

        Args:
            user_authorities: 사용자 권한 목록
            agent_filter: 에이전트 필터 (예: "lge_caia", "lge_raih")

        Returns:
            권한이 있는지 여부
        """
        try:
            user_authority_str = ""
            service_use_yn = None

            for user_authority in user_authorities:
                authority_code = user_authority.get("authority_code", "")

                if user_authority_str == "":
                    user_authority_str = authority_code
                else:
                    user_authority_str = user_authority_str + ", " + authority_code

                # AUTH_GRP_01 서비스 사용 불가
                if authority_code == "AUTH_GRP_01":
                    service_use_yn = False
                    break
                # 요청한 권한이 있으면 서비스 사용 가능
                elif authority_code == agent_filter:
                    service_use_yn = True

            self.logger.info(f"[AUTH] 사용자 권한 목록: {user_authority_str}")
            self.logger.info(f"[AUTH] 서비스 사용 가능 여부: {service_use_yn}")

            return service_use_yn is True

        except Exception as e:
            self.logger.error(f"[AUTH] 권한 검증 실패: {e}")
            return False

    def validate_user_session(self, user_info: Dict[str, Any]) -> bool:
        """
        사용자 세션 유효성 검증

        Args:
            user_info: 사용자 정보

        Returns:
            세션이 유효한지 여부
        """
        try:
            # 기본적인 유효성 검사
            if not user_info or not user_info.get("user_id"):
                return False

            # 추가적인 검증 로직 구현 가능
            # 예: 토큰 만료 시간 확인, 사용자 권한 확인 등

            return True

        except Exception as e:
            self.logger.error(f"[AUTH] 사용자 세션 유효성 검증 실패: {e}")
            return False


# 전역 인스턴스
authorization_service = AuthorizationService()
