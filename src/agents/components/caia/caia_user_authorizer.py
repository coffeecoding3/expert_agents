"""
CAIA User Authorizer

CAIA 에이전트를 위한 사용자 인증 및 권한 관리
다중 데이터베이스 연결을 통한 사용자 정보 조회 및 권한 확인
"""

from __future__ import annotations

import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import mysql.connector
from mysql.connector import pooling
from mysql.connector.errors import Error as MySQLError

# 프로젝트 루트를 Python 경로에 추가
sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent))

from configs.app_config import load_config
from src.apps.api.user.user_manager import UserManager
from src.database.services import membership_service, user_service
from src.memory.memory_manager import memory_manager
from src.schemas.user_schemas import UserInfo, user_info_to_dict
from src.utils.db_utils import get_db_session

logger = logging.getLogger("caia.user_authorizer")


class UserRole(Enum):
    """사용자 역할"""

    ADMIN = "admin"
    USER = "user"


@dataclass
class AgentMembership:
    """에이전트 멤버십 정보"""

    user_id: int
    agent_id: int
    role: str
    enabled: bool
    expires_at: Optional[str]
    agent_name: str
    agent_code: str


class CAIAUserAuthorizer:
    """CAIA 사용자 인증 및 권한 관리 클래스"""

    # 특정 사용자 목록 (하드코딩된 특별 권한 사용자들)
    SPECIAL_USERS = ["hojae114.jung", "hq15", "hq31", "hq21", "hq27"]

    def __init__(self):
        """초기화"""
        self.config = load_config()
        self.main_db_provider = None
        self.iam_db_provider = None
        self.user_manager = UserManager()
        self._init_database_connections()

    def _init_database_connections(self):
        """데이터베이스 연결 초기화"""
        try:
            # 메인 데이터베이스 연결 (expert_agents)
            main_config = self._get_main_db_config()
            self.main_db_provider = self._create_mysql_provider(main_config, "main_db")
            logger.debug("[DATABASE] 메인 데이터베이스 연결 성공")

            # IAM 데이터베이스 연결 (next_iam)
            iam_config = self._get_iam_db_config()
            if iam_config:
                self.iam_db_provider = self._create_mysql_provider(iam_config, "iam_db")
                logger.debug("[DATABASE] IAM 데이터베이스 연결 성공")
            else:
                logger.warning("[DATABASE] IAM 데이터베이스 설정이 없습니다.")

        except Exception as e:
            logger.error(f"[DATABASE] 데이터베이스 연결 초기화 실패: {e}")
            raise

    def _get_main_db_config(self) -> Dict[str, Any]:
        """메인 데이터베이스 설정 가져오기"""
        db_config = self.config.get("database", {}).get("main", {})
        return {
            "host": db_config.get("host", "localhost"),
            "port": int(db_config.get("port", 3306)),
            "user": db_config.get("user", "user"),
            "password": db_config.get("password", "password"),
            "database": db_config.get("database", "expert_agents"),
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
            "use_unicode": True,
            "autocommit": True,
            "raise_on_warnings": False,
            "sql_mode": "TRADITIONAL,NO_AUTO_VALUE_ON_ZERO",
        }

    def _get_iam_db_config(self) -> Optional[Dict[str, Any]]:
        """IAM 데이터베이스 설정 가져오기"""
        db_config = self.config.get("database", {}).get("iam", {})
        host = db_config.get("host")
        if not host:
            return None

        return {
            "host": host,
            "port": int(db_config.get("port", 3306)),
            "user": db_config.get("user"),
            "password": db_config.get("password"),
            "database": db_config.get("database"),
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
            "use_unicode": True,
            "autocommit": True,
            "raise_on_warnings": False,
            "sql_mode": "TRADITIONAL,NO_AUTO_VALUE_ON_ZERO",
        }

    def _create_mysql_provider(self, config: Dict[str, Any], pool_name: str):
        """MySQL 프로바이더 생성"""
        try:
            # 연결 풀 설정
            pool_size = config.get("pool_size", 5)
            config.update(
                {
                    "pool_size": pool_size,
                    "pool_reset_session": True,
                    "pool_name": f"{pool_name}_pool",
                    "charset": "utf8mb4",
                    "use_unicode": True,
                }
            )

            # MySQL 연결 풀 생성
            pool = mysql.connector.pooling.MySQLConnectionPool(**config)
            return pool

        except MySQLError as e:
            logger.error(f"MySQL 연결 풀 생성 실패 ({pool_name}): {e}")
            raise

    @contextmanager
    def _get_db_connection(self, provider_name: str):
        """데이터베이스 연결 컨텍스트 매니저"""
        provider = getattr(self, f"{provider_name}_db_provider")
        if not provider:
            raise ValueError(f"{provider_name} 데이터베이스 연결이 없습니다.")

        connection = None
        cursor = None
        try:
            connection = provider.get_connection()
            cursor = connection.cursor(dictionary=True)
            # 문자 인코딩 설정
            cursor.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute("SET CHARACTER SET utf8mb4")
            yield cursor
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _ensure_utf8_string(self, value: Any) -> Any:
        """문자열을 UTF-8로 보장"""
        if isinstance(value, str):
            try:
                # 이미 UTF-8로 인코딩된 문자열인지 확인
                value.encode("utf-8").decode("utf-8")
                return value
            except UnicodeError:
                # 여러 인코딩으로 디코딩 시도
                for encoding in ["latin1", "cp1252", "iso-8859-1"]:
                    try:
                        return value.encode(encoding).decode("utf-8")
                    except (UnicodeError, UnicodeDecodeError):
                        continue
                # 모든 시도가 실패하면 원본 반환
                return value
        return value

    def _save_personnel_memory(self, user_db_id: int, user_info: UserInfo) -> None:
        """인사정보 메모리 저장 (공통 메서드)"""
        try:
            user_dict = user_info_to_dict(user_info)
            self.user_manager.update_personnel_memory_async(user_db_id, user_dict)
            logger.debug(
                f"[MEMORY] 인사정보 메모리 비동기 저장 시작: user_id={user_db_id}"
            )
        except Exception as e:
            logger.error(f"[MEMORY] 인사정보 메모리 저장 실패: {e}")

    def _create_user_info_from_db_result(
        self, user_result: Dict[str, Any], user_id: str
    ) -> UserInfo:
        """데이터베이스 결과로부터 UserInfo 객체 생성"""
        with self._get_db_connection("main") as cursor:
            user_groups, user_drafts, user_setting, user_authorities = (
                self._get_user_related_info(user_id, cursor)
            )

        return UserInfo(
            creation_user_id=self._ensure_utf8_string(user_result["creation_user_id"]),
            creation_date=self._ensure_utf8_string(user_result["creation_date"]),
            last_update_user_id=self._ensure_utf8_string(
                user_result["last_update_user_id"]
            ),
            last_update_date=self._ensure_utf8_string(user_result["last_update_date"]),
            user_id=self._ensure_utf8_string(user_result["user_id"]),
            username=self._ensure_utf8_string(user_result["username"]),
            username_eng=self._ensure_utf8_string(user_result["username_eng"]),
            email=self._ensure_utf8_string(user_result["email"]),
            is_admin=self._ensure_utf8_string(user_result["is_admin"]),
            use_yn=user_result["use_yn"],
            nationality=self._ensure_utf8_string(user_result["nationality"]),
            division=self._ensure_utf8_string(user_result["division"]),
            organ=self._ensure_utf8_string(user_result["organ"]),
            organ_name=self._ensure_utf8_string(user_result["organ_name"]),
            location=self._ensure_utf8_string(user_result["location"]),
            division1_nm=self._ensure_utf8_string(user_result["division1_nm"]),
            division2_nm=self._ensure_utf8_string(user_result["division2_nm"]),
            approval_status=self._ensure_utf8_string(user_result["approval_status"]),
            sabun=self._ensure_utf8_string(user_result["sabun"]),
            authority_group_code=self._ensure_utf8_string(
                user_result["authority_group_code"]
            ),
            authority_code="lge_caia",
            # 추가 HR 데이터 필드들
            name=self._ensure_utf8_string(user_result.get("name")),
            jikwi=self._ensure_utf8_string(user_result.get("jikwi")),
            sf_user_id=self._ensure_utf8_string(user_result.get("sf_user_id")),
            employee_category=self._ensure_utf8_string(
                user_result.get("employee_category")
            ),
            job_name=self._ensure_utf8_string(user_result.get("job_name")),
            jikchek_name=self._ensure_utf8_string(user_result.get("jikchek_name")),
            jikwi_name=self._ensure_utf8_string(user_result.get("jikwi_name")),
            user_groups=user_groups,
            user_drafts=user_drafts,
            user_setting=user_setting,
            user_authorities=user_authorities,
        )

    def get_user_info(self, user_id: str) -> Optional[UserInfo]:
        """사용자 정보 조회 (엘지니 SSO 방식)"""
        try:
            # 먼저 메인 DB에서 사용자 정보 조회
            user_info = self._get_user_from_main_db(user_id)
            if user_info:
                return user_info

            # 메인 DB에 없으면 IAM DB에서 조회하여 새로 생성
            return self._create_user_from_iam_db(user_id)

        except Exception as e:
            logger.error(f"사용자 정보 조회 실패 (user_id: {user_id}): {e}")
            return None

    def _get_user_from_main_db(self, user_id: str) -> Optional[UserInfo]:
        """메인 DB에서 사용자 정보 조회"""
        if not self.main_db_provider:
            return None

        try:
            with self._get_db_connection("main") as cursor:
                user_query = """
                SELECT 
                    creation_user_id, creation_date, last_update_user_id, last_update_date,
                    user_id, username, username_eng, email, is_admin, use_yn,
                    nationality, division, organ, organ_name, location,
                    division1_nm, division2_nm, approval_status, sabun, authority_group_code,
                    name, jikwi, sf_user_id, employee_category, job_name, jikchek_name, jikwi_name
                FROM users 
                WHERE user_id = %s
                """
                cursor.execute(user_query, (user_id,))
                user_result = cursor.fetchone()

                if user_result:
                    return self._create_user_info_from_db_result(user_result, user_id)
                return None

        except Exception as e:
            logger.error(f"메인 DB에서 사용자 조회 실패: {e}")
            return None

    def _create_user_from_iam_db(self, user_id: str) -> Optional[UserInfo]:
        """IAM DB에서 사용자 정보를 조회하여 새 사용자 생성"""
        if not self.iam_db_provider:
            logger.error("[DATABASE] IAM 데이터베이스 연결이 없습니다.")
            return None

        try:
            with self._get_db_connection("iam") as cursor:
                hr_query = """
                SELECT 
                    ssoid, name, name_eng, email, nationality, division, organ, organ_name, location,
                    division1_nm, division2_nm, sabun, htgubun, SSO_YN, management_organ,
                    jikwi, sf_user_id, employee_category, job_name, jikchek_name, jikwi_name
                FROM dap_lge_hr_data 
                WHERE ssoid = %s AND (htgubun = 'A' OR htgubun = 'C')
                """
                cursor.execute(hr_query, (user_id,))
                hr_result = cursor.fetchone()

                if not hr_result:
                    logger.error(f"IAM DB에서 사용자를 찾을 수 없습니다: {user_id}")
                    return None

                # HR 데이터를 기반으로 UserInfo 객체 생성
                current_time = time.strftime("%Y-%m-%dT%H:%M:%S")
                authority_group_code = self._determine_authority_group(hr_result)

                user_info = UserInfo(
                    creation_user_id="system",
                    creation_date=current_time,
                    last_update_user_id="system",
                    last_update_date=current_time,
                    user_id=hr_result["ssoid"],
                    username=hr_result["name"],
                    username_eng=hr_result["name_eng"],
                    email=hr_result["email"],
                    is_admin="user",
                    use_yn=True,
                    nationality=hr_result["nationality"],
                    division=hr_result["division"],
                    organ=hr_result["organ"],
                    organ_name=hr_result["organ_name"],
                    location=hr_result["location"],
                    division1_nm=hr_result["division1_nm"],
                    division2_nm=hr_result["division2_nm"],
                    approval_status="approved",
                    sabun=hr_result["sabun"],
                    authority_group_code=authority_group_code,
                    authority_code="lge_caia",
                    # 추가 HR 데이터 필드들
                    name=hr_result["name"],
                    jikwi=hr_result["jikwi"],
                    sf_user_id=hr_result["sf_user_id"],
                    employee_category=hr_result["employee_category"],
                    job_name=hr_result["job_name"],
                    jikchek_name=hr_result["jikchek_name"],
                    jikwi_name=hr_result["jikwi_name"],
                    user_groups=[],
                    user_drafts=[],
                    user_setting={},
                    user_authorities=[
                        {
                            "creation_user_id": "system",
                            "creation_date": current_time,
                            "last_update_user_id": None,
                            "last_update_date": None,
                            "authority_group_code": authority_group_code,
                            "authority_code": "lge_caia",
                            "authority_type": "COMPANY_TYPE",
                            "message_filter": "LGE",
                            "chat_filter": "LGSSCHAT",
                        }
                    ],
                )

                # 로컬 DB에 사용자 저장
                self._save_user_to_main_db(user_info)
                return user_info

        except Exception as e:
            logger.error(f"IAM DB에서 사용자 생성 실패: {e}")
            return None

    def _save_user_to_main_db(self, user_info: UserInfo) -> int:
        """로컬 DB에 사용자 정보 저장 (ORM 사용)"""
        try:
            with get_db_session() as db:
                # 기존 사용자 조회
                existing_user = user_service.get_by_user_id(db, user_info.user_id)

                if existing_user:
                    # 기존 사용자 업데이트
                    user_db_id = self._update_existing_user(
                        db, existing_user.id, user_info
                    )
                else:
                    # 새 사용자 생성
                    user_db_id = self._create_new_user(db, user_info)

                # 에이전트 멤버십 생성/업데이트 (CAIA 에이전트 ID = 1)
                membership_service.create_or_update_membership(
                    db, user_db_id, 1, UserRole.USER.value, True, None
                )

                logger.debug(
                    f"[DATABASE] 사용자 정보를 로컬 DB에 저장 완료: {user_info.user_id}"
                )

                # 인사정보를 semantic 메모리에 비동기로 저장
                self._save_personnel_memory(user_db_id, user_info)
                return user_db_id

        except Exception as e:
            logger.error(f"[DATABASE] 로컬 DB에 사용자 저장 실패: {e}")
            raise

    def _update_existing_user(self, db, user_id: int, user_info: UserInfo) -> int:
        """기존 사용자 정보 업데이트"""
        update_data = {
            "username": user_info.username,
            "name": user_info.name,
            "employee_category": user_info.employee_category,
            "last_update_date": user_info.last_update_date,
            "username_eng": user_info.username_eng,
            "email": user_info.email,
            "is_admin": user_info.is_admin,
            "use_yn": user_info.use_yn,
            "nationality": user_info.nationality,
            "division": user_info.division,
            "organ": user_info.organ,
            "organ_name": user_info.organ_name,
            "location": user_info.location,
            "division1_nm": user_info.division1_nm,
            "division2_nm": user_info.division2_nm,
            "approval_status": user_info.approval_status,
            "sabun": user_info.sabun,
            "authority_group_code": user_info.authority_group_code,
            "jikwi": user_info.jikwi,
            "sf_user_id": user_info.sf_user_id,
            "job_name": user_info.job_name,
            "jikchek_name": user_info.jikchek_name,
            "jikwi_name": user_info.jikwi_name,
        }
        user_service.update_user_info(db, user_id, update_data)
        return user_id

    def _create_new_user(self, db, user_info: UserInfo) -> int:
        """새 사용자 생성"""
        new_user = user_service.create(
            db,
            creation_user_id=user_info.creation_user_id,
            creation_date=user_info.creation_date,
            last_update_user_id=user_info.last_update_user_id,
            last_update_date=user_info.last_update_date,
            user_id=user_info.user_id,
            username=user_info.username,
            username_eng=user_info.username_eng,
            email=user_info.email,
            is_admin=user_info.is_admin,
            use_yn=user_info.use_yn,
            nationality=user_info.nationality,
            division=user_info.division,
            organ=user_info.organ,
            organ_name=user_info.organ_name,
            location=user_info.location,
            division1_nm=user_info.division1_nm,
            division2_nm=user_info.division2_nm,
            approval_status=user_info.approval_status,
            sabun=user_info.sabun,
            authority_group_code=user_info.authority_group_code,
            name=user_info.name,
            jikwi=user_info.jikwi,
            sf_user_id=user_info.sf_user_id,
            employee_category=user_info.employee_category,
            job_name=user_info.job_name,
            jikchek_name=user_info.jikchek_name,
            jikwi_name=user_info.jikwi_name,
        )
        return new_user.id

    def _get_user_related_info(self, user_id: str, cursor) -> tuple:
        """사용자 관련 정보 조회 (설정, 권한)"""
        try:
            # 사용자 설정 조회
            user_setting = self._get_user_settings(user_id, cursor)

            # 사용자 권한 조회
            user_authorities = self._get_user_authorities(user_id, cursor)

            # user_groups와 user_drafts는 테이블이 존재하지 않으므로 빈 리스트 반환
            return [], [], user_setting, user_authorities

        except Exception as e:
            logger.error(f"[DATABASE] 사용자 관련 정보 조회 실패: {e}")
            return [], [], {}, []

    def _get_user_settings(self, user_id: str, cursor) -> Dict[str, Any]:
        """사용자 설정 조회"""
        default_settings = {
            "summary_yn": True,
            "topk": 5,
            "response_order": "summary",
            "duplicate_search": True,
            "genai_model": None,
            "common_document_yn": False,
            "genai_model_name": None,
            "image_generation_yn": None,
            "image_analysis_yn": None,
            "interface_systems": [],
        }

        try:
            settings_query = """
            SELECT 
                summary_yn, topk, response_order, duplicate_search, genai_model,
                common_document_yn, genai_model_name, image_generation_yn,
                image_analysis_yn, interface_systems
            FROM user_settings WHERE user_id = %s
            """
            cursor.execute(settings_query, (user_id,))
            settings_result = cursor.fetchone()

            if settings_result:
                default_settings.update(
                    {
                        "summary_yn": settings_result.get("summary_yn", True),
                        "topk": settings_result.get("topk", 5),
                        "response_order": settings_result.get(
                            "response_order", "summary"
                        ),
                        "duplicate_search": settings_result.get(
                            "duplicate_search", True
                        ),
                        "genai_model": settings_result.get("genai_model"),
                        "common_document_yn": settings_result.get(
                            "common_document_yn", False
                        ),
                        "genai_model_name": settings_result.get("genai_model_name"),
                        "image_generation_yn": settings_result.get(
                            "image_generation_yn"
                        ),
                        "image_analysis_yn": settings_result.get("image_analysis_yn"),
                        "interface_systems": settings_result.get(
                            "interface_systems", []
                        ),
                    }
                )
        except Exception:
            pass  # user_settings 테이블이 없으면 기본값 사용

        return default_settings

    def _get_user_authorities(self, user_id: str, cursor) -> List[Dict[str, Any]]:
        """사용자 권한 조회"""
        try:
            authorities_query = """
            SELECT 
                uam.user_id, uam.agent_id, uam.role, uam.enabled, uam.expires_at,
                'AUTH_GRP_07' as authority_group_code, 
                CONCAT('lge_', LOWER(a.code)) as authority_code,
                'COMPANY_TYPE' as authority_type, 'LGE' as message_filter, 'LGSSCHAT' as chat_filter
            FROM user_agent_memberships uam
            JOIN users u ON uam.user_id = u.id
            JOIN agents a ON uam.agent_id = a.id
            WHERE u.user_id = %s AND uam.enabled = 1 AND a.is_active = 1
            """
            cursor.execute(authorities_query, (user_id,))
            authorities_results = cursor.fetchall()

            return [
                {
                    "creation_user_id": "system",
                    "creation_date": "2025-02-14T13:15:54",
                    "last_update_user_id": None,
                    "last_update_date": None,
                    "authority_group_code": result["authority_group_code"],
                    "authority_code": result["authority_code"],
                    "authority_type": result["authority_type"],
                    "message_filter": result["message_filter"],
                    "chat_filter": result["chat_filter"],
                }
                for result in authorities_results
            ]

        except Exception as e:
            logger.error(f"[DATABASE] 사용자 권한 조회 실패: {e}")
            return []

    def check_caia_authority(self, user_id: str) -> bool:
        """CAIA 권한 확인"""
        try:
            user_info = self.get_user_info(user_id)
            if not user_info:
                return False

            # 임원이거나 특정 사용자인지 확인
            if user_info.employee_category == "임원":
                return True
            elif user_info.user_id in self.SPECIAL_USERS:
                # 특정 사용자들에 대해서도 인사정보 메모리 저장 확인
                self._ensure_special_user_memory(user_id, user_info)
                return True

            # membership 테이블에서 CAIA 에이전트 멤버십 확인
            if self._check_membership_authority(user_id):
                return True
            else:
                return False

        except Exception as e:
            logger.error(f"[DATABASE] CAIA 권한 확인 실패 (user_id: {user_id}): {e}")
            return False

    def _check_membership_authority(self, user_id: str) -> bool:
        """membership 테이블에서 CAIA 에이전트 멤버십 확인"""
        try:
            with get_db_session() as db:
                from sqlalchemy import text

                # CAIA 에이전트 ID 조회 (code가 'CAIA'인 에이전트)
                agent_query = text(
                    """
                    SELECT id FROM agents WHERE code = 'CAIA' LIMIT 1
                """
                )
                agent_result = db.execute(agent_query)
                agent_row = agent_result.fetchone()

                if not agent_row:
                    logger.warning("[MEMBERSHIP] CAIA 에이전트를 찾을 수 없습니다.")
                    return False

                caia_agent_id = agent_row[0]

                # 사용자의 CAIA 에이전트 멤버십 확인
                membership_query = text(
                    """
                    SELECT uam.enabled, uam.expires_at 
                    FROM user_agent_memberships uam
                    JOIN users u ON uam.user_id = u.id
                    WHERE u.user_id = :user_id AND uam.agent_id = :agent_id
                """
                )

                result = db.execute(
                    membership_query, {"user_id": user_id, "agent_id": caia_agent_id}
                )
                membership_row = result.fetchone()

                if not membership_row:
                    logger.debug(
                        f"[MEMBERSHIP] 사용자 {user_id}의 CAIA 멤버십이 없습니다."
                    )
                    return False

                enabled, expires_at = membership_row

                # 멤버십이 활성화되어 있는지 확인
                if not enabled:
                    logger.error(
                        f"[MEMBERSHIP] 사용자 {user_id}의 CAIA 멤버십이 비활성화되어 있습니다."
                    )
                    return False

                # 만료일 확인 (만료일이 설정된 경우)
                if expires_at:
                    from datetime import datetime

                    try:
                        expires_date = datetime.fromisoformat(
                            expires_at.replace("Z", "+00:00")
                        )
                        if expires_date < datetime.now():
                            logger.error(
                                f"[MEMBERSHIP] 사용자 {user_id}의 CAIA 멤버십이 만료되었습니다."
                            )
                            return False
                    except Exception as e:
                        logger.warning(f"[MEMBERSHIP] 만료일 파싱 실패: {e}")

                logger.info(
                    f"[MEMBERSHIP] 사용자 {user_id}의 CAIA 멤버십이 활성화되어 있습니다."
                )
                return True

        except Exception as e:
            logger.error(f"[MEMBERSHIP] 멤버십 확인 실패 (user_id: {user_id}): {e}")
            return False

    def _ensure_special_user_memory(self, user_id: str, user_info: UserInfo) -> None:
        """특정 사용자들의 인사정보 메모리 저장 확인 및 실행"""
        try:
            # 데이터베이스에서 사용자 ID 조회
            with get_db_session() as db:
                db_user = user_service.get_by_user_id(db, user_id)
                if not db_user:
                    logger.error(
                        f"[MEMORY] 사용자 {user_id}의 데이터베이스 레코드를 찾을 수 없습니다."
                    )
                    return
                user_db_id = db_user.id

            # 메모리 매니저 초기화 확인 및 필요시 초기화
            if not memory_manager.provider:
                logger.warning("메모리 프로바이더가 초기화되지 않음, 초기화 시도")
                try:
                    from src.memory.memory_manager import initialize_memory_manager

                    initialize_memory_manager()
                    if not memory_manager.provider:
                        logger.error(
                            "메모리 프로바이더 초기화 실패, 특정 사용자 메모리 저장 건너뜀"
                        )
                        return
                except Exception as e:
                    logger.error(f"메모리 프로바이더 초기화 중 오류: {e}")
                    return

            # CAIA 에이전트 ID 가져오기
            agent_id = memory_manager.get_agent_id_by_code("caia")
            if not agent_id:
                logger.error("CAIA 에이전트 ID를 찾을 수 없습니다.")
                return

            # 사용자의 기존 인사정보 메모리 확인
            existing_memories = memory_manager.get_recent_memories(
                user_id=user_db_id, agent_id=agent_id, limit=10
            )

            # 인사정보 메모리가 이미 있는지 확인
            has_personnel_memory = any(
                memory.get("category") == "인사정보" for memory in existing_memories
            )

            if not has_personnel_memory:
                # 사용자 정보를 딕셔너리로 변환
                user_dict = user_info_to_dict(user_info)

                # 인사정보 메모리 비동기 저장
                self.user_manager.update_personnel_memory_async(user_db_id, user_dict)

            else:
                logger.debug(
                    f"[MEMORY] 특정 사용자 {user_id}의 인사정보 메모리가 이미 존재함"
                )

        except Exception as e:
            logger.error(
                f"[MEMORY] 특정 사용자 {user_id}의 인사정보 메모리 저장 중 오류: {e}"
            )

    def _determine_authority_group(self, hr_result: Dict[str, Any]) -> str:
        """HR 정보를 바탕으로 권한 그룹 코드 결정"""
        try:
            sabun = hr_result.get("sabun", "")
            sso_yn = hr_result.get("SSO_YN", "")
            management_organ = hr_result.get("management_organ", "")

            if sabun.startswith("X"):
                # X로 시작하는 사번 (협력사)
                if sso_yn == "Y":
                    logger.debug("[DATABASE] EAIP 관련 관리자 승인 그룹 확인")
                    return "AUTH_GRP_07"
                elif management_organ in ["307107", "355941"]:
                    logger.debug("[DATABASE] EAIP 관련 협력사 접속 확인")
                    return "AUTH_GRP_02"
                else:
                    logger.debug("[DATABASE] 협력사 로그인 불가, X-sabun limited")
                    return "AUTH_GRP_01"
            else:
                # 일반 직원
                return "AUTH_GRP_02"

        except Exception as e:
            logger.error(f"[DATABASE] 권한 그룹 결정 실패: {e}")
            return "AUTH_GRP_01"

    def close(self):
        """리소스 정리"""
        try:
            if self.user_manager:
                self.user_manager.close()
            logger.debug("CAIA User Authorizer가 종료되었습니다.")
        except Exception as e:
            logger.error(f"CAIA User Authorizer 종료 중 오류: {e}")


# 전역 인스턴스 (싱글톤 패턴)
_authorizer_instance = None


def get_authorizer() -> CAIAUserAuthorizer:
    """싱글톤 인스턴스 반환"""
    global _authorizer_instance
    if _authorizer_instance is None:
        _authorizer_instance = CAIAUserAuthorizer()
    return _authorizer_instance


if __name__ == "__main__":
    authorizer = get_authorizer()
    user_info = authorizer.get_user_info(user_id="test_user")
