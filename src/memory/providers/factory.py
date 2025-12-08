"""
Memory Provider Factory

메모리 프로바이더 생성을 위한 팩토리 패턴
"""

from logging import getLogger
from typing import Any, Dict, Optional

from .mysql_provider import MySQLMemoryProvider
from .redis_provider import RedisMemoryProvider

logger = getLogger("memory.factory")


class MemoryProviderFactory:
    """메모리 프로바이더 팩토리"""

    def create_provider(self, config: Dict[str, Any]) -> Optional[Any]:
        """설정에 따라 메모리 프로바이더 인스턴스를 생성합니다."""
        provider_name = config.get("provider", "").lower()

        if provider_name == "mysql":
            try:
                # MySQL 연결 설정에서 'provider' 키 제거
                connection_config = {k: v for k, v in config.items() if k != "provider"}
                return MySQLMemoryProvider(connection_config)
            except Exception as e:
                logger.error(f"MySQL 프로바이더 생성 실패: {e}")
                return None
        elif provider_name == "redis":
            try:
                return RedisMemoryProvider(config)
            except Exception as e:
                logger.error(f"Redis 프로바이더 생성 실패: {e}")
                return None
        else:
            logger.error(f"지원하지 않는 프로바이더 타입: {provider_name}")
            return None

    @staticmethod
    def get_mysql_config_from_url(database_url: str) -> Dict[str, Any]:
        """MySQL URL에서 연결 설정 추출

        Args:
            database_url: MySQL 연결 URL

        Returns:
            MySQL 연결 설정 딕셔너리
        """
        try:
            if not (
                database_url.startswith("mysql://")
                or database_url.startswith("mysql+pymysql://")
            ):
                raise ValueError("올바른 MySQL URL 형식이 아닙니다.")

            # mysql:// 또는 mysql+pymysql:// 제거
            if database_url.startswith("mysql+pymysql://"):
                url_part = database_url[16:]
            else:
                url_part = database_url[8:]

            if "@" in url_part:
                auth_part, host_part = url_part.split("@", 1)
                if ":" in auth_part:
                    username, password = auth_part.split(":", 1)
                else:
                    username, password = auth_part, ""
            else:
                username, password = "", ""
                host_part = url_part

            if "/" in host_part:
                host_port, database = host_part.split("/", 1)
                if ":" in host_port:
                    host, port = host_port.split(":", 1)
                    port = int(port)
                else:
                    host, port = host_port, 3306
            else:
                host, port = host_part, 3306
                database = ""

            return {
                "host": host,
                "port": port,
                "user": username,
                "password": password,
                "database": database,
                "charset": "utf8mb4",
                "collation": "utf8mb4_unicode_ci",
                "autocommit": True,
                "raise_on_warnings": True,
            }

        except Exception as e:
            logger.error(f"MySQL URL 파싱 실패: {e}")
            raise ValueError(f"MySQL URL 파싱 실패: {e}")

    @staticmethod
    def validate_config(provider_type: str, config: Dict[str, Any]) -> bool:
        """프로바이더 설정 유효성 검사

        Args:
            provider_type: 프로바이더 타입
            config: 프로바이더 설정

        Returns:
            설정 유효성 여부
        """
        if provider_type.lower() == "mysql":
            required_keys = ["host", "port", "user", "database"]
            return all(key in config for key in required_keys)
        elif provider_type.lower() == "redis":
            # redis_url 또는 host/port 중 하나로 충분
            return bool(
                config.get("redis_url") or (config.get("host") and config.get("port"))
            )
        elif provider_type.lower() == "mongo":
            # uri 또는 host/port/database
            return bool(
                config.get("uri")
                or (
                    config.get("host") and config.get("port") and config.get("database")
                )
            )
        else:
            return False
