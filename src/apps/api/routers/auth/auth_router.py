"""
Authentication Router for CAIA Service

SSO 로그인 및 사용자 인증 처리
"""

import json
import os
from logging import getLogger
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.apps.api.user.user_service import user_auth_service
from src.database.connection.dependencies import get_database_session
from src.database.models.models import Agent, User
from src.database.services.agent_services import (
    agent_service,
    membership_service,
)
from src.database.services.database_service import database_service
from src.database.services.orm_service import membership_service
from src.database.services.user_services import user_service
from src.schemas.user_schemas import UserInfoResponse

logger = getLogger("auth")


# =============================================================================
# Pydantic Models for Swagger Documentation
# =============================================================================


class AgentData(BaseModel):
    """에이전트 데이터 모델"""
    
    creation_user_id: str = Field(..., description="생성 사용자 ID")
    creation_date: str = Field(..., description="생성 일시")
    last_update_user_id: str = Field(..., description="최종 수정 사용자 ID")
    last_update_date: str = Field(..., description="최종 수정 일시")
    id: int = Field(..., description="에이전트 ID")
    assistant_ai_id: str = Field(..., description="에이전트 코드")
    assistant_ai_name: str = Field(..., description="에이전트 이름")
    assistant_ai_url: str = Field(..., description="에이전트 URL")
    description: str = Field(..., description="에이전트 설명 (lang에 따라 ko/en)")
    tag: str = Field(..., description="태그")
    lang: str = Field(..., description="응답 언어")
    priority: int = Field(..., description="우선순위")
    use_yn: bool = Field(..., description="사용 여부")
    open_yn: bool = Field(..., description="공개 여부")
    agent_filter: str = Field(..., description="에이전트 필터")
    base64image: str = Field(..., description="이미지 (base64)")
    width: int = Field(..., description="이미지 너비")
    height: int = Field(..., description="이미지 높이")
    
    class Config:
        json_schema_extra = {
            "example": {
                "creation_user_id": "system",
                "creation_date": "2024-12-04T13:01:23",
                "last_update_user_id": "system",
                "last_update_date": "2024-12-04T13:01:23",
                "id": 1,
                "assistant_ai_id": "CAIA",
                "assistant_ai_name": "Chief AI Advisor",
                "assistant_ai_url": "",
                "description": "C레벨 임원전용 AI 어드바이저",
                "tag": "COM",
                "lang": "ko",
                "priority": 1,
                "use_yn": True,
                "open_yn": True,
                "agent_filter": "LGE",
                "base64image": "",
                "width": 0,
                "height": 0
            }
        }


class AgentsListResponse(BaseModel):
    """에이전트 목록 조회 응답 모델"""
    
    status: bool = Field(..., description="성공 여부")
    message: str = Field(..., description="응답 메시지")
    last_session_time: Optional[str] = Field(None, description="마지막 세션 시간")
    expire_second: float = Field(..., description="만료 시간 (초)")
    data: list[AgentData] = Field(..., description="에이전트 목록")
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": True,
                "message": "요청에 성공하였습니다.",
                "last_session_time": None,
                "expire_second": 21600.0,
                "data": [
                    {
                        "creation_user_id": "system",
                        "creation_date": "2024-12-04T13:01:23",
                        "last_update_user_id": "system",
                        "last_update_date": "2024-12-04T13:01:23",
                        "id": 1,
                        "assistant_ai_id": "CAIA",
                        "assistant_ai_name": "Chief AI Advisor",
                        "assistant_ai_url": "",
                        "description": "C레벨 임원전용 AI 어드바이저",
                        "tag": "COM",
                        "lang": "ko",
                        "priority": 1,
                        "use_yn": True,
                        "open_yn": True,
                        "agent_filter": "LGE",
                        "base64image": "",
                        "width": 0,
                        "height": 0
                    }
                ]
            }
        }


# 개발/테스트 환경 설정
APP_ENV = os.getenv("APP_ENV", "production").lower()
# Swagger 테스트용 사용자 DB ID (환경변수에서 주석 제거)
_swagger_test_user_id_raw = os.getenv("SWAGGER_TEST_USER_ID", None)
if _swagger_test_user_id_raw:
    # 주석이나 공백 제거 (예: "9999  # 주석" -> "9999")
    SWAGGER_TEST_USER_ID = _swagger_test_user_id_raw.split("#")[0].strip()
else:
    SWAGGER_TEST_USER_ID = None


class SSOLoginResponse(BaseModel):
    """SSO 로그인 응답 모델"""

    status: bool
    message: str
    last_session_time: Optional[str] = None
    expire_second: float = 21600.0
    data: Optional[Dict[str, Any]] = None


# 동적 에이전트 인증 라우터 (path parameter 사용) - CAIA 포함
agent_auth_router = APIRouter(
    prefix="/{agent_code}/api/v1/user", tags=["Agent Authentication"]
)

# 에이전트 목록 조회 전용 라우터 (agent_code 상관없이)
agents_list_router = APIRouter(prefix="/api/v1", tags=["Agents List"])


def extract_user_from_cookies(request: Request) -> Optional[UserInfoResponse]:
    """
    요청의 쿠키에서 사용자 정보 추출

    Args:
        request: FastAPI Request 객체

    Returns:
        UserInfoResponse 객체 또는 None
    """
    try:
        # ssolgenet_exa 쿠키 찾기
        ssolgenet_exa = request.cookies.get("ssolgenet_exa")
        if not ssolgenet_exa:
            logger.warning("ssolgenet_exa cookie not found")
            return None

        # 사용자 서비스를 통해 쿠키 파싱
        # extract_user_from_cookies는 agent_code를 받지 않으므로 기본값 사용
        user_data = user_auth_service.get_user_from_cookie(
            ssolgenet_exa, agent_filter="lge_caia", agent_code="caia"
        )
        if not user_data:
            return None

        # UserInfoResponse 객체 생성
        return UserInfoResponse(
            user_id=user_data.get("user_id", "unknown"),
            username=user_data.get("username", "unknown"),
            display_name=user_data.get("username", "Unknown User"),
            initials=(
                user_data.get("username", "U")[:2].upper()
                if user_data.get("username")
                else "U"
            ),
            color=user_data.get("color"),
        )

    except Exception as e:
        logger.error(f"Failed to extract user from cookies: {e}")
        return None


# =============================================================================
# 동적 에이전트 인증 라우터 (path parameter 사용) - CAIA 포함
# =============================================================================


@agent_auth_router.get("/sso_login")
async def agent_sso_login(
    agent_code: str, request: Request, ssolgenet_exa: Optional[str] = None
) -> SSOLoginResponse:
    """
    동적 에이전트 SSO 로그인 처리

    쿠키에서 사용자 정보를 추출하여 로그인 처리

    Args:
        agent_code: 에이전트 코드 (path parameter)
        ssolgenet_exa: SSO 쿠키 값 (테스트용 쿼리 파라미터)
    """
    try:
        # 쿠키에서 사용자 정보 추출 (쿼리 파라미터 우선, 없으면 쿠키에서)
        cookie_value = ssolgenet_exa or request.cookies.get("ssolgenet_exa", "")
        agent_filter = f"lge_{agent_code.lower()}"
        user_data = user_auth_service.get_user_from_cookie(
            cookie_value, agent_filter=agent_filter, agent_code=agent_code.lower()
        )

        if not user_data:
            return SSOLoginResponse(
                status=False,
                message="사용자 정보를 찾을 수 없습니다. 로그인이 필요합니다.",
            )

        # 데이터베이스 저장 및 메모리 업데이트 결과 확인
        db_user_id = user_data.get("db_user_id")
        if not db_user_id:
            logger.warning(
                f"[AUTH] {agent_code.upper()} 사용자 데이터베이스 저장 또는 메모리 업데이트 실패"
            )

        return SSOLoginResponse(
            status=True,
            message="요청에 성공하였습니다.",
            last_session_time=None,
            expire_second=21600.0,
            data=user_data,
        )

    except Exception as e:
        logger.error(f"[AUTH] {agent_code.upper()} SSO 로그인 오류: {e}")
        return SSOLoginResponse(
            status=False, message=f"로그인 처리 중 오류가 발생했습니다: {str(e)}"
        )


@agent_auth_router.get("/user_info")
async def agent_get_user_info(agent_code: str, request: Request) -> Dict[str, Any]:
    """
    동적 에이전트 현재 사용자 정보 조회
    """
    try:
        agent_filter = f"lge_{agent_code.lower()}"
        user_data = user_auth_service.get_user_from_cookie(
            request.cookies.get("ssolgenet_exa", ""),
            agent_filter=agent_filter,
            agent_code=agent_code.lower(),
        )

        if not user_data:
            raise HTTPException(
                status_code=401, detail="사용자 정보를 찾을 수 없습니다."
            )

        # 데이터베이스 저장 및 메모리 업데이트 결과 확인
        db_user_id = user_data.get("db_user_id")
        if not db_user_id:
            logger.warning(
                f"[AUTH] {agent_code.upper()} 사용자 데이터베이스 저장 또는 메모리 업데이트 실패"
            )

        return user_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AUTH] {agent_code.upper()} 사용자 정보 조회 실패: {e}")
        raise HTTPException(
            status_code=500, detail="사용자 정보 조회 중 오류가 발생했습니다."
        )


@agent_auth_router.post("/logout")
async def agent_logout(agent_code: str, request: Request) -> Dict[str, Any]:
    """
    동적 에이전트 로그아웃 처리
    """
    try:
        # 세션 쿠키 제거 등의 로그아웃 로직 구현
        return {
            "success": True,
            "message": f"{agent_code.upper()} 로그아웃이 완료되었습니다.",
        }

    except Exception as e:
        logger.error(f"[AUTH] {agent_code.upper()} 로그아웃 오류: {e}")
        raise HTTPException(
            status_code=500, detail="로그아웃 처리 중 오류가 발생했습니다."
        )


@agent_auth_router.get("/debug/cookies")
async def agent_debug_cookies(agent_code: str, request: Request) -> Dict[str, Any]:
    """
    동적 에이전트 쿠키 디버깅용 엔드포인트 (개발용)
    """
    try:
        # 모든 쿠키 정보 수집
        all_cookies = dict(request.cookies)

        # ssolgenet_exa 쿠키 특별 처리
        ssolgenet_exa = request.cookies.get("ssolgenet_exa")
        parsed_data = None
        if ssolgenet_exa:
            parsed_data = user_auth_service.parse_ssolgenet_exa_cookie(ssolgenet_exa)

        # 사용자 정보 조회
        agent_filter = f"lge_{agent_code.lower()}"
        user_data = (
            user_auth_service.get_user_from_cookie(
                ssolgenet_exa,
                agent_filter=agent_filter,
                agent_code=agent_code.lower(),
            )
            if ssolgenet_exa
            else None
        )

        return {
            "agent_code": agent_code,
            "all_cookies": all_cookies,
            "ssolgenet_exa_raw": ssolgenet_exa,
            "ssolgenet_exa_parsed": parsed_data,
            "user_info": user_data,
        }

    except Exception as e:
        logger.error(f"[AUTH] {agent_code.upper()} 쿠키 디버깅 오류: {e}")
        raise HTTPException(
            status_code=500, detail=f"쿠키 디버깅 중 오류가 발생했습니다: {str(e)}"
        )


# =============================================================================
# 에이전트 목록 조회 라우터 (agent_code 상관없이)
# =============================================================================


@agents_list_router.get(
    "/agents/list",
    response_model=AgentsListResponse,
    summary="에이전트 목록 조회",
    description="""
    에이전트 목록 조회 API
    
    쿠키 기반 인증을 통해 권한이 있는 에이전트 목록을 반환합니다.
    
    **Query Parameters:**
    - `lang`: 응답 언어 설정 ("ko" 또는 "en", 선택사항, 기본값: "ko")
      - "ko": 한국어 description 반환
      - "en": 영어 description_en 반환 (없으면 description fallback)
    
    **Response:**
    - `status`: 성공 여부
    - `message`: 응답 메시지
    - `data`: 에이전트 목록 배열
      - 각 에이전트의 `description` 필드는 `lang` 파라미터에 따라 한국어 또는 영어로 반환됩니다.
    """,
    responses={
        200: {
            "description": "에이전트 목록 조회 성공",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/AgentsListResponse"}
                }
            }
        }
    }
)
async def get_agents_list(
    request: Request,
    lang: Optional[str] = Query(
        default="ko",
        description="응답 언어 설정 (ko: 한국어, en: 영어)",
        example="ko"
    ),
    db: Session = Depends(get_database_session)
) -> AgentsListResponse:
    """
    에이전트 목록 조회

    쿠키 기반 인증을 통해 권한이 있는 에이전트 목록을 반환합니다.
    Request body의 lang 파라미터에 따라 description 또는 description_en을 반환합니다.
    """
    try:
        # Query parameter에서 lang 파라미터 읽기 (기본값: "ko")
        # lang이 "ko" 또는 "en"이 아니면 기본값 "ko" 사용
        if lang not in ["ko", "en"]:
            lang = "ko"
        
        # 쿠키에서 사용자 정보 추출
        # get_agents_list는 agent_code를 받지 않으므로 기본값 사용
        cookie_value = request.cookies.get("ssolgenet_exa", "")
        user_data = user_auth_service.get_user_from_cookie(
            cookie_value, agent_filter="lge_caia", agent_code="caia"
        )

        available_agents = []
        db_session = None

        # DB 세션 가져오기
        try:
            if hasattr(db, "__next__"):
                db_session = next(db)
            else:
                db_session = db
        except Exception as e:
            logger.error(f"[AUTH] DB 세션 가져오기 실패: {e}")
            db_session = None

        # 쿠키가 없거나 사용자 정보가 없을 때 (Swagger 테스트용 - 개발 환경에서만)
        if not user_data:
            # 개발 환경이고 테스트 사용자가 설정된 경우에만 작동
            if APP_ENV in ["development", "dev", "test"] and SWAGGER_TEST_USER_ID:
                try:
                    test_user_db_id = int(SWAGGER_TEST_USER_ID)
                    logger.info(
                        f"[AUTH] 쿠키 없음 - 테스트 사용자로 대체: db_user_id={test_user_db_id} (개발 환경 전용)"
                    )

                    # 테스트 사용자의 멤버십 기반으로 에이전트 조회
                    user_memberships = membership_service.get_user_agents(
                        db_session, test_user_db_id
                    )

                    logger.info(
                        f"[AUTH] 테스트 사용자 멤버십 조회: user_id={test_user_db_id}, {len(user_memberships)}개 멤버십 발견"
                    )

                    # 멤버십이 없는 경우 사용자와 멤버십 등록
                    if not user_memberships:
                        logger.info(
                            f"[AUTH] 테스트 사용자 {test_user_db_id}의 활성 멤버십이 없습니다. "
                            f"사용자와 멤버십을 등록합니다."
                        )
                        # 사용자 확인 및 생성
                        user = db_session.query(User).filter(User.id == test_user_db_id).first()
                        if not user:
                            logger.info(
                                f"[AUTH] 테스트 사용자 ID {test_user_db_id}를 찾을 수 없습니다. "
                                f"사용자 등록이 필요합니다."
                            )
                            # 테스트 사용자 생성 시도
                            try:
                                new_user = User(
                                    user_id=f"test_user_{test_user_db_id}",
                                    username=f"Test User {test_user_db_id}",
                                    use_yn=True,
                                )
                                db_session.add(new_user)
                                db_session.commit()
                                db_session.refresh(new_user)
                                test_user_db_id = new_user.id
                                logger.info(
                                    f"[AUTH] 새 테스트 사용자 생성 완료: db_user_id={test_user_db_id}"
                                )
                                user = new_user
                            except Exception as e:
                                logger.error(
                                    f"[AUTH] 테스트 사용자 생성 실패: {e}", exc_info=True
                                )
                                user = None
                        
                        # 사용자가 있으면 모든 활성 에이전트에 대한 멤버십 생성
                        if user:
                            active_agents = agent_service.get_active_agents(db_session)
                            logger.info(
                                f"[AUTH] 활성 에이전트 조회: {len(active_agents)}개 발견"
                            )
                            created_count = 0
                            for agent in active_agents:
                                membership = membership_service.create_or_update_membership(
                                    db=db_session,
                                    user_id=test_user_db_id,
                                    agent_id=agent.id,
                                    role="member",
                                    enabled=True,
                                    expires_at=None,
                                )
                                if membership:
                                    created_count += 1
                                    logger.info(
                                        f"[AUTH] 테스트 사용자 {test_user_db_id}에게 agent {agent.code} (ID: {agent.id}) 멤버십 추가 완료"
                                    )
                            logger.info(
                                f"[AUTH] 테스트 사용자 {test_user_db_id}에게 {created_count}개의 agent 멤버십이 추가되었습니다."
                            )
                            # 멤버십 재조회
                            user_memberships = membership_service.get_user_agents(
                                db_session, test_user_db_id
                            )
                            logger.info(
                                f"[AUTH] 멤버십 재조회: {len(user_memberships)}개 멤버십 발견"
                            )
                        else:
                            logger.error(
                                f"[AUTH] 테스트 사용자를 찾을 수 없거나 생성할 수 없어 멤버십을 생성할 수 없습니다."
                            )
                    else:
                        for membership in user_memberships:
                            agent_id = membership.agent_id
                            logger.debug(
                                f"[AUTH] 테스트 사용자 멤버십 처리: agent_id={agent_id}, enabled={membership.enabled}"
                            )
                            agent = (
                                db_session.query(Agent)
                                .filter(Agent.id == agent_id, Agent.is_active == True)
                                .first()
                            )
                            if agent:
                                available_agents.append(
                                    {
                                        "id": agent.id,
                                        "name": agent.name,
                                        "code": agent.code,
                                        "description": agent.description,
                                        "description_en": agent.description_en,
                                        "created_at": agent.created_at,
                                        "updated_at": agent.updated_at,
                                        "is_active": agent.is_active,
                                    }
                                )
                            else:
                                # 에이전트가 없거나 비활성화된 경우 상세 로깅
                                inactive_agent = (
                                    db_session.query(Agent)
                                    .filter(Agent.id == agent_id)
                                    .first()
                                )
                                if inactive_agent:
                                    logger.warning(
                                        f"[AUTH] 테스트 사용자: 에이전트 ID {agent_id} (code={inactive_agent.code}) "
                                        f"가 비활성화되어 있습니다 (is_active={inactive_agent.is_active})"
                                    )
                                else:
                                    logger.warning(
                                        f"[AUTH] 테스트 사용자: 에이전트 ID {agent_id}를 찾을 수 없습니다"
                                    )
                    
                    logger.info(
                        f"[AUTH] 테스트 모드: {len(available_agents)}개 에이전트 조회 완료"
                    )
                except ValueError:
                    logger.warning(
                        f"[AUTH] SWAGGER_TEST_USER_ID가 유효한 정수가 아닙니다: {SWAGGER_TEST_USER_ID}"
                    )
                except Exception as e:
                    logger.error(f"[AUTH] 테스트 사용자 에이전트 조회 실패: {e}")
            else:
                # 프로덕션 환경이거나 테스트 사용자가 설정되지 않은 경우
                logger.warning(
                    "[AUTH] 쿠키가 없고 테스트 사용자도 설정되지 않음 - 빈 리스트 반환"
                )
                return AgentsListResponse(
                    status=False,
                    message="사용자 정보를 찾을 수 없습니다.",
                    last_session_time=None,
                    expire_second=21600.0,
                    data=[],
                )
        else:
            # 쿠키가 있는 경우: 사용자 멤버십 기반으로 조회
            user_id = user_data.get("user_id")
            db_user_id = user_data.get("db_user_id")
            logger.info(
                f"[AUTH] 사용자 정보 확인: user_id={user_id}, db_user_id={db_user_id}"
            )

            # db_user_id가 None이면 user_id로 사용자 조회
            if not db_user_id and user_id and db_session:
                try:
                    user = user_service.get_by_user_id(db_session, user_id)
                    if user:
                        db_user_id = user.id
                        logger.info(
                            f"[AUTH] user_id로 db_user_id 조회 성공: user_id={user_id} -> db_user_id={db_user_id}"
                        )
                    else:
                        logger.warning(
                            f"[AUTH] user_id로 사용자를 찾을 수 없습니다: user_id={user_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"[AUTH] user_id로 사용자 조회 실패: {e}", exc_info=True
                    )

            # 사용자가 접근 가능한 에이전트 조회
            if db_user_id and db_session:
                try:
                    # user_agent_memberships 테이블에서 해당 user_id가 권한있는 agent들 조회
                    user_memberships = membership_service.get_user_agents(
                        db_session, db_user_id
                    )

                    logger.info(
                        f"[AUTH] 사용자 멤버십 조회: user_id={db_user_id}, {len(user_memberships)}개 멤버십 발견"
                    )

                    # 멤버십이 없는 경우 사용자와 멤버십 등록
                    if not user_memberships:
                        logger.info(
                            f"[AUTH] 사용자 {db_user_id}의 활성 멤버십이 없습니다. "
                            f"사용자와 멤버십을 등록합니다."
                        )
                        # 사용자 확인 및 생성
                        user = db_session.query(User).filter(User.id == db_user_id).first()
                        if not user:
                            logger.info(
                                f"[AUTH] 사용자 ID {db_user_id}를 찾을 수 없습니다. "
                                f"사용자 등록이 필요합니다. user_id={user_id}"
                            )
                            # 사용자 정보가 있으면 사용자 생성 시도
                            if user_id:
                                try:
                                    new_user = User(
                                        user_id=user_id,
                                        username=user_data.get("username", user_id),
                                        email=user_data.get("email"),
                                        use_yn=True,
                                    )
                                    db_session.add(new_user)
                                    db_session.commit()
                                    db_session.refresh(new_user)
                                    db_user_id = new_user.id
                                    logger.info(
                                        f"[AUTH] 새 사용자 생성 완료: db_user_id={db_user_id}, user_id={user_id}"
                                    )
                                    user = new_user
                                except Exception as e:
                                    logger.error(
                                        f"[AUTH] 사용자 생성 실패: {e}", exc_info=True
                                    )
                                    user = None
                        
                        # 사용자가 있으면 모든 활성 에이전트에 대한 멤버십 생성
                        if user:
                            active_agents = agent_service.get_active_agents(db_session)
                            logger.info(
                                f"[AUTH] 활성 에이전트 조회: {len(active_agents)}개 발견"
                            )
                            created_count = 0
                            for agent in active_agents:
                                membership = membership_service.create_or_update_membership(
                                    db=db_session,
                                    user_id=db_user_id,
                                    agent_id=agent.id,
                                    role="member",
                                    enabled=True,
                                    expires_at=None,
                                )
                                if membership:
                                    created_count += 1
                                    logger.info(
                                        f"[AUTH] 사용자 {db_user_id}에게 agent {agent.code} (ID: {agent.id}) 멤버십 추가 완료"
                                    )
                            logger.info(
                                f"[AUTH] 사용자 {db_user_id}에게 {created_count}개의 agent 멤버십이 추가되었습니다."
                            )
                            # 멤버십 재조회
                            user_memberships = membership_service.get_user_agents(
                                db_session, db_user_id
                            )
                            logger.info(
                                f"[AUTH] 멤버십 재조회: {len(user_memberships)}개 멤버십 발견"
                            )
                        else:
                            logger.error(
                                f"[AUTH] 사용자를 찾을 수 없거나 생성할 수 없어 멤버십을 생성할 수 없습니다."
                            )
                    else:
                        # 멤버십에서 agent_id 추출하여 available_agents에 추가
                        for membership in user_memberships:
                            agent_id = membership.agent_id
                            logger.debug(
                                f"[AUTH] 멤버십 처리: agent_id={agent_id}, enabled={membership.enabled}"
                            )
                            # 해당 agent_id로 agent 정보 조회
                            agent = (
                                db_session.query(Agent)
                                .filter(Agent.id == agent_id, Agent.is_active == True)
                                .first()
                            )
                            if agent:
                                available_agents.append(
                                    {
                                        "id": agent.id,
                                        "name": agent.name,
                                        "code": agent.code,
                                        "description": agent.description,
                                        "description_en": agent.description_en,
                                        "created_at": agent.created_at,
                                        "updated_at": agent.updated_at,
                                        "is_active": agent.is_active,
                                    }
                                )
                                logger.debug(
                                    f"[AUTH] 에이전트 추가: id={agent.id}, code={agent.code}, name={agent.name}"
                                )
                            else:
                                # 에이전트가 없거나 비활성화된 경우 상세 로깅
                                inactive_agent = (
                                    db_session.query(Agent)
                                    .filter(Agent.id == agent_id)
                                    .first()
                                )
                                if inactive_agent:
                                    logger.warning(
                                        f"[AUTH] 에이전트 ID {agent_id} (code={inactive_agent.code}) "
                                        f"가 비활성화되어 있습니다 (is_active={inactive_agent.is_active})"
                                    )
                                else:
                                    logger.warning(
                                        f"[AUTH] 에이전트 ID {agent_id}를 찾을 수 없습니다"
                                    )
                        
                        logger.info(
                            f"[AUTH] 최종 에이전트 목록: {len(available_agents)}개"
                        )
                except Exception as e:
                    logger.error(
                        f"[AUTH] 사용자 에이전트 멤버십 조회 실패: {e}", exc_info=True
                    )
                    available_agents = []
            else:
                logger.warning(
                    f"[AUTH] db_user_id가 None이거나 빈 값입니다: db_user_id={db_user_id}, "
                    f"db_session={'있음' if db_session else '없음'}"
                )

        # 세션 정리 (제너레이터에서 가져온 경우만 닫기)
        if db_session and hasattr(db, "__next__") and hasattr(db_session, "close"):
            try:
                db_session.close()
            except Exception as e:
                logger.warning(f"[AUTH] 세션 정리 중 오류: {e}")

        # 응답 데이터 구성
        agents_data = []

        # TODO: 임시로 CAIA만 보여주는 로직 (추후 제거 예정)
        # 2. 데이터베이스의 에이전트들을 변환하여 추가
        for agent_record in available_agents:
            # TODO: CAIA만 필터링 (추후 제거 예정)
            agent_code = agent_record.get("code", "").upper()
            if agent_code != "CAIA":
                logger.debug(
                    f"[AUTH] CAIA가 아닌 에이전트 필터링됨: {agent_code}"
                )
                continue
            # lang에 따라 description 또는 description_en 선택
            if lang == "en":
                description_value = agent_record.get("description_en") or agent_record.get("description") or ""
            else:
                description_value = agent_record.get("description") or ""
            
            agent_data = {
                "creation_user_id": "system",
                "creation_date": (
                    agent_record["created_at"].isoformat()
                    if agent_record.get("created_at")
                    else "2024-12-04T13:01:23"
                ),
                "last_update_user_id": "system",
                "last_update_date": (
                    agent_record["updated_at"].isoformat()
                    if agent_record.get("updated_at")
                    else "2024-12-04T13:01:23"
                ),
                "id": agent_record["id"],
                "assistant_ai_id": agent_record["code"].upper(),
                "assistant_ai_name": agent_record["name"],
                "assistant_ai_url": "",
                "description": description_value,
                "tag": "COM",
                "lang": lang,
                "priority": agent_record["id"],  # ID를 priority로 사용
                "use_yn": bool(agent_record.get("is_active")),
                "open_yn": bool(agent_record.get("is_active")),
                "agent_filter": "LGE",
                "base64image": "",
                "width": 0,
                "height": 0,
            }
            agents_data.append(agent_data)

        return AgentsListResponse(
            status=True,
            message="요청에 성공하였습니다.",
            last_session_time=None,
            expire_second=21600.0,
            data=[AgentData(**agent) for agent in agents_data],
        )

    except Exception as e:
        logger.error(f"[AUTH] 에이전트 목록 조회 오류: {e}")
        return AgentsListResponse(
            status=False,
            message=f"에이전트 목록 조회 중 오류가 발생했습니다: {str(e)}",
            last_session_time=None,
            expire_second=21600.0,
            data=[],
        )
