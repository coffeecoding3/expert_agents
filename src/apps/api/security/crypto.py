"""
Crypto utilities for SSO authentication

LG전자 SSO 쿠키 복호화를 위한 암호화 유틸리티
"""

import base64
from datetime import datetime, timedelta, timezone
from logging import getLogger
from typing import Optional

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

logger = getLogger("crypto")


class SSOAuthenticationException(Exception):
    """SSO 인증 예외"""

    def __init__(
        self,
        message: str = "SSO 인증에 실패했습니다.",
        status_code: int = 401,
        url: Optional[str] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.url = url
        super().__init__(self.message)


def decrypt_aes256(encrypted_data: str) -> str:
    """
    AES256으로 암호화된 SSO 데이터 복호화

    Args:
        encrypted_data: Base64로 인코딩된 암호화된 데이터

    Returns:
        복호화된 사용자 ID

    Raises:
        SSOAuthenticationException: 복호화 실패 시
    """
    try:
        # 설정 파일에서 SSO 키 가져오기
        from configs.app_config import load_config

        config = load_config()
        sso_config = config.get("security", {}).get("sso", {})

        sso_key = sso_config.get("key")
        if not sso_key:
            logger.error(
                "SSO_KEY가 설정되지 않았습니다. 환경변수 SSO_KEY 또는 설정 파일을 확인하세요."
            )
            raise SSOAuthenticationException("SSO 설정 오류")

        # 허용된 시간 차이 (분)
        allowed_time_diff_minutes = sso_config.get("allowed_time_diff_minutes", 720)

        key_bytes = sso_key.encode("utf-8")
        encrypted_data = base64.b64decode(encrypted_data)

        # IV는 암호화된 데이터의 처음 16 바이트에 저장됨
        iv = encrypted_data[:16]
        encrypted_data = encrypted_data[16:]

        # 타임스탬프는 마지막 14바이트
        timestamp_bytes = encrypted_data[-14:]
        timestamp = timestamp_bytes.decode("utf-8")

        # 암호문
        cipher_text = encrypted_data[:-14]

        # 타임스탬프 유효성 검증
        timestamp_format = "%Y%m%d%H%M%S"
        timestamp_date = datetime.strptime(timestamp, timestamp_format).replace(
            tzinfo=timezone.utc
        )
        now = datetime.now(timezone.utc)
        time_diff = now - timestamp_date

        if time_diff > timedelta(minutes=allowed_time_diff_minutes):
            raise SSOAuthenticationException("SSO 토큰이 만료되었습니다.")

        # AES/CBC/PKCS5Padding으로 복호화
        cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
        decrypted_data = unpad(cipher.decrypt(cipher_text), AES.block_size)

        # 복호화된 데이터에서 타임스탬프 제거하여 순수한 사용자 ID만 반환
        decrypted_str = decrypted_data.decode("utf-8")
        # 타임스탬프는 14자리 (YYYYMMDDHHMMSS)이므로 마지막 14자리를 제거
        if len(decrypted_str) > 14:
            user_id = decrypted_str[:-14]
        else:
            user_id = decrypted_str

        return user_id

    except SSOAuthenticationException:
        raise
    except Exception as e:
        logger.error(f"SSO 데이터 복호화 실패: {e}")
        raise SSOAuthenticationException("SSO 인증에 실패했습니다.")
