"""
SSO Cookie Parser

SSO 쿠키 파싱 및 사용자 정보 추출을 담당하는 모듈
"""

import base64
import json
import urllib.parse
from logging import getLogger
from typing import Any, Dict, Optional

logger = getLogger("sso_parser")


class SSOCookieParser:
    """SSO 쿠키 파서"""

    def __init__(self):
        self.logger = logger

    def parse_ssolgenet_exa_cookie(self, cookie_value: str) -> Optional[Dict[str, Any]]:
        """
        ssolgenet_exa 쿠키 값을 파싱하여 사용자 정보 추출

        예시 쿠키 값: id%3D2PBZJ1R4oQKD%2FuGLDQcyaDGP0HTlyxQanOI6dCcsKRoyMDI1MDkxNjA0MTcyOA%3D%3D

        Args:
            cookie_value: URL 인코딩된 쿠키 값

        Returns:
            파싱된 사용자 정보 딕셔너리 또는 None
        """
        try:
            # URL 디코딩
            decoded_value = urllib.parse.unquote(cookie_value)
            self.logger.info(f"[SSO_PARSER] URL 디코딩된 쿠키 값: {decoded_value}")

            # Base64 디코딩 시도
            try:
                # Base64 디코딩
                decoded_bytes = base64.b64decode(decoded_value)
                decoded_str = decoded_bytes.decode("utf-8")
                self.logger.info(f"[SSO_PARSER] Base64 디코딩된 값: {decoded_str}")

                # JSON 파싱 시도 (만약 JSON 형태라면)
                try:
                    user_data = json.loads(decoded_str)
                    self.logger.info(f"[SSO_PARSER] 파싱된 JSON 데이터: {user_data}")
                    return user_data
                except json.JSONDecodeError:
                    # JSON이 아닌 경우, 단순 문자열로 처리
                    self.logger.info(
                        "[SSO_PARSER] 데이터가 JSON 형식이 아니므로 원본 문자열로 처리"
                    )
                    return {"raw_data": decoded_str}

            except Exception as e:
                self.logger.warning(f"[SSO_PARSER] Base64 디코딩 실패: {e}")
                # Base64 디코딩 실패 시 원본 디코딩된 값 반환
                return {"raw_data": decoded_value}

        except Exception as e:
            self.logger.error(f"[SSO_PARSER] ssolgenet_exa 쿠키 파싱 실패: {e}")
            return None

    def extract_user_info_from_raw_data(
        self, raw_data: str
    ) -> Optional[Dict[str, Any]]:
        """
        raw_data에서 사용자 정보 추출

        예시 raw_data: "id=2PBZJ1R4oQKD/uGLDQcyaDGP0HTlyxQanOI6dCcsKRoyMDI1MDkxNjA0MTcyOA=="

        Args:
            raw_data: 파싱된 원본 데이터

        Returns:
            사용자 정보 딕셔너리 또는 None
        """
        try:
            self.logger.info(f"[SSO_PARSER] 사용자 정보 추출 시작: {raw_data}")

            # raw_data가 "id=..." 형태인지 확인
            if raw_data.startswith("id="):
                # id 값 추출
                id_value = raw_data[3:]  # "id=" 제거
                self.logger.info(f"[SSO_PARSER] 추출된 id 값: {id_value}")

                # id_value를 다시 Base64 디코딩 시도
                try:
                    decoded_id = base64.b64decode(id_value).decode("utf-8")
                    self.logger.info(f"[SSO_PARSER] 디코딩된 id 값: {decoded_id}")

                    # 디코딩된 값에서 사용자 정보 추출
                    # 실제 구조에 따라 파싱 로직 구현
                    # 예시: decoded_id가 JSON 형태라면 파싱
                    try:
                        user_data = json.loads(decoded_id)
                        return {
                            "user_id": user_data.get("user_id", "unknown"),
                            "username": user_data.get("username", "unknown"),
                            "display_name": user_data.get(
                                "display_name", "Unknown User"
                            ),
                            "initials": user_data.get("initials"),
                            "color": user_data.get("color"),
                            "raw_data": raw_data,
                            "decoded_id": decoded_id,
                        }
                    except json.JSONDecodeError:
                        # JSON이 아닌 경우, 단순 문자열로 처리
                        return {
                            "user_id": decoded_id,
                            "username": decoded_id,
                            "display_name": f"User {decoded_id}",
                            "initials": (
                                decoded_id[:2].upper() if len(decoded_id) >= 2 else "U"
                            ),
                            "raw_data": raw_data,
                            "decoded_id": decoded_id,
                        }

                except Exception as e:
                    self.logger.warning(f"[SSO_PARSER] id 값 디코딩 실패: {e}")
                    # 디코딩 실패 시 원본 id_value 사용
                    return {
                        "user_id": id_value,
                        "username": id_value,
                        "display_name": f"User {id_value}",
                        "initials": "U",
                        "raw_data": raw_data,
                    }
            else:
                # "id=" 형태가 아닌 경우, 전체를 사용자 ID로 처리
                return {
                    "user_id": raw_data,
                    "username": raw_data,
                    "display_name": f"User {raw_data}",
                    "initials": "U",
                    "raw_data": raw_data,
                }

        except Exception as e:
            self.logger.error(f"[SSO_PARSER] 사용자 정보 추출 실패: {e}")
            return None


# 전역 인스턴스
sso_parser = SSOCookieParser()
