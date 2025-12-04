"""
API Key 관리 라우터

API Key 발급, 조회, 관리 등을 위한 관리 API
"""

from datetime import datetime
from logging import getLogger
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.connection import get_database_session
from src.database.models import APIKey
from src.database.services.api_key_service import api_key_service

logger = getLogger("api_key_router")

# API Key 관리 라우터
api_key_router = APIRouter(
    prefix="/api/v1/api-keys",
    tags=["API Key 관리"],
    responses={
        401: {"description": "인증 실패"},
        403: {"description": "권한 없음"},
        404: {"description": "API Key를 찾을 수 없습니다"},
        500: {"description": "서버 내부 오류"},
    },
)


# 스키마 정의
class APIKeyCreateRequest(BaseModel):
    """API Key 생성 요청"""

    name: Optional[str] = Field(None, description="키 이름/설명")
    expires_in_days: Optional[int] = Field(
        None, description="만료일 (일 단위, None이면 만료 없음)"
    )
    agent_codes: Optional[List[str]] = Field(
        None, description="접근 가능한 Agent 코드 목록 (None이면 모든 agent 접근 가능)"
    )


class APIKeyResponse(BaseModel):
    """API Key 응답"""

    id: int
    name: Optional[str]
    is_active: bool
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    agent_codes: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class APIKeyCreateResponse(BaseModel):
    """API Key 생성 응답"""

    api_key: str = Field(..., description="생성된 API Key (평문, 한 번만 표시)")
    key_info: APIKeyResponse


class APIKeyListResponse(BaseModel):
    """API Key 목록 응답"""

    total: int
    keys: List[APIKeyResponse]


@api_key_router.post(
    "/",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="API Key 생성",
    description="새로운 API Key를 생성합니다. 생성된 키는 한 번만 표시되므로 안전하게 보관하세요.",
)
async def create_api_key(
    request: APIKeyCreateRequest,
    db: Session = Depends(get_database_session),
) -> APIKeyCreateResponse:
    """
    API Key 생성

    Args:
        request: API Key 생성 요청
        db: 데이터베이스 세션

    Returns:
        APIKeyCreateResponse: 생성된 API Key 정보
    """
    try:
        plain_key, api_key_obj = api_key_service.create_api_key(
            db=db,
            name=request.name,
            expires_in_days=request.expires_in_days,
            agent_codes=request.agent_codes,
        )

        if not plain_key or not api_key_obj:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API Key 생성에 실패했습니다.",
            )

        # Agent 코드 목록 조회
        db.refresh(api_key_obj, ["agent_permissions"])
        agent_codes = [
            perm.agent.code for perm in api_key_obj.agent_permissions if perm.agent
        ]

        return APIKeyCreateResponse(
            api_key=plain_key,
            key_info=APIKeyResponse(
                id=api_key_obj.id,
                name=api_key_obj.name,
                is_active=api_key_obj.is_active,
                expires_at=api_key_obj.expires_at,
                last_used_at=api_key_obj.last_used_at,
                created_at=api_key_obj.created_at,
                agent_codes=agent_codes,
            ),
        )

    except Exception as e:
        logger.error(f"[API_KEY_ROUTER] API Key 생성 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API Key 생성 중 오류가 발생했습니다: {str(e)}",
        )


@api_key_router.get(
    "/",
    response_model=APIKeyListResponse,
    summary="API Key 목록 조회",
    description="등록된 API Key 목록을 조회합니다.",
)
async def list_api_keys(
    include_inactive: bool = False,
    agent_code: Optional[str] = None,
    db: Session = Depends(get_database_session),
) -> APIKeyListResponse:
    """
    API Key 목록 조회

    Args:
        include_inactive: 비활성화된 키 포함 여부
        agent_code: 특정 Agent에 대한 권한이 있는 키만 조회
        db: 데이터베이스 세션

    Returns:
        APIKeyListResponse: API Key 목록
    """
    try:
        keys = api_key_service.list_keys(
            db=db, include_inactive=include_inactive, agent_code=agent_code
        )

        key_responses = []
        for key in keys:
            # Agent 코드 목록 조회
            db.refresh(key, ["agent_permissions"])
            agent_codes = [
                perm.agent.code for perm in key.agent_permissions if perm.agent
            ]

            key_responses.append(
                APIKeyResponse(
                    id=key.id,
                    name=key.name,
                    is_active=key.is_active,
                    expires_at=key.expires_at,
                    last_used_at=key.last_used_at,
                    created_at=key.created_at,
                    agent_codes=agent_codes,
                )
            )

        return APIKeyListResponse(total=len(key_responses), keys=key_responses)

    except Exception as e:
        logger.error(f"[API_KEY_ROUTER] API Key 목록 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API Key 목록 조회 중 오류가 발생했습니다: {str(e)}",
        )


@api_key_router.get(
    "/{key_id}",
    response_model=APIKeyResponse,
    summary="API Key 상세 조회",
    description="특정 API Key의 상세 정보를 조회합니다.",
)
async def get_api_key(
    key_id: int,
    db: Session = Depends(get_database_session),
) -> APIKeyResponse:
    """
    API Key 상세 조회

    Args:
        key_id: API Key ID
        db: 데이터베이스 세션

    Returns:
        APIKeyResponse: API Key 정보
    """
    try:
        from src.database.models import APIKey

        api_key = db.query(APIKey).filter(APIKey.id == key_id).first()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API Key (ID: {key_id})를 찾을 수 없습니다.",
            )

        # Agent 코드 목록 조회
        db.refresh(api_key, ["agent_permissions"])
        agent_codes = [
            perm.agent.code for perm in api_key.agent_permissions if perm.agent
        ]

        return APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            is_active=api_key.is_active,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
            agent_codes=agent_codes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API_KEY_ROUTER] API Key 조회 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API Key 조회 중 오류가 발생했습니다: {str(e)}",
        )


@api_key_router.post(
    "/{key_id}/deactivate",
    response_model=APIKeyResponse,
    summary="API Key 비활성화",
    description="API Key를 비활성화합니다.",
)
async def deactivate_api_key(
    key_id: int,
    db: Session = Depends(get_database_session),
) -> APIKeyResponse:
    """
    API Key 비활성화

    Args:
        key_id: API Key ID
        db: 데이터베이스 세션

    Returns:
        APIKeyResponse: 비활성화된 API Key 정보
    """
    try:
        from src.database.models import APIKey

        api_key = db.query(APIKey).filter(APIKey.id == key_id).first()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API Key (ID: {key_id})를 찾을 수 없습니다.",
            )

        success = api_key_service.deactivate_key(db=db, key_id=key_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="API Key 비활성화에 실패했습니다.",
            )

        # 최신 정보 조회
        db.refresh(api_key, ["agent_permissions"])
        agent_codes = [
            perm.agent.code for perm in api_key.agent_permissions if perm.agent
        ]

        return APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            is_active=api_key.is_active,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
            agent_codes=agent_codes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API_KEY_ROUTER] API Key 비활성화 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"API Key 비활성화 중 오류가 발생했습니다: {str(e)}",
        )


@api_key_router.post(
    "/{key_id}/agent-permissions",
    response_model=APIKeyResponse,
    summary="Agent 권한 추가",
    description="API Key에 Agent 접근 권한을 추가합니다.",
)
async def add_agent_permission(
    key_id: int,
    agent_code: str,
    db: Session = Depends(get_database_session),
) -> APIKeyResponse:
    """
    Agent 권한 추가

    Args:
        key_id: API Key ID
        agent_code: Agent 코드
        db: 데이터베이스 세션

    Returns:
        APIKeyResponse: 업데이트된 API Key 정보
    """
    try:
        from src.database.models import APIKey

        api_key = db.query(APIKey).filter(APIKey.id == key_id).first()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API Key (ID: {key_id})를 찾을 수 없습니다.",
            )

        success = api_key_service.add_agent_permission(
            db=db, api_key_id=key_id, agent_code=agent_code
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent 권한 추가에 실패했습니다: {agent_code}",
            )

        # 최신 정보 조회
        db.refresh(api_key, ["agent_permissions"])
        agent_codes = [
            perm.agent.code for perm in api_key.agent_permissions if perm.agent
        ]

        return APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            is_active=api_key.is_active,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
            agent_codes=agent_codes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API_KEY_ROUTER] Agent 권한 추가 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent 권한 추가 중 오류가 발생했습니다: {str(e)}",
        )


@api_key_router.delete(
    "/{key_id}/agent-permissions/{agent_code}",
    response_model=APIKeyResponse,
    summary="Agent 권한 제거",
    description="API Key에서 Agent 접근 권한을 제거합니다.",
)
async def remove_agent_permission(
    key_id: int,
    agent_code: str,
    db: Session = Depends(get_database_session),
) -> APIKeyResponse:
    """
    Agent 권한 제거

    Args:
        key_id: API Key ID
        agent_code: Agent 코드
        db: 데이터베이스 세션

    Returns:
        APIKeyResponse: 업데이트된 API Key 정보
    """
    try:
        from src.database.models import APIKey

        api_key = db.query(APIKey).filter(APIKey.id == key_id).first()

        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API Key (ID: {key_id})를 찾을 수 없습니다.",
            )

        success = api_key_service.remove_agent_permission(
            db=db, api_key_id=key_id, agent_code=agent_code
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Agent 권한 제거에 실패했습니다: {agent_code}",
            )

        # 최신 정보 조회
        db.refresh(api_key, ["agent_permissions"])
        agent_codes = [
            perm.agent.code for perm in api_key.agent_permissions if perm.agent
        ]

        return APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            is_active=api_key.is_active,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
            agent_codes=agent_codes,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API_KEY_ROUTER] Agent 권한 제거 실패: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Agent 권한 제거 중 오류가 발생했습니다: {str(e)}",
        )
