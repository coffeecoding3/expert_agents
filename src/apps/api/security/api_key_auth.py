"""
API Key 인증 모듈

Agent별 API Key 검증을 위한 모듈
"""

from logging import getLogger
from typing import Optional

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from src.database.connection import get_database_session
from src.database.models import APIKey
from src.database.services.api_key_service import api_key_service

logger = getLogger("api_key_auth")


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key", description="API Key"),
    db: Session = Depends(get_database_session),
    agent_code: Optional[str] = None,
) -> APIKey:
    """
    API Key 검증 의존성 함수

    Args:
        x_api_key: X-API-Key 헤더에서 추출한 API Key
        db: 데이터베이스 세션
        agent_code: Agent 코드 (예: "lexai", "caia"). None이면 권한 체크 없음

    Returns:
        APIKey: 유효한 API Key 객체

    Raises:
        HTTPException: API Key가 없거나 유효하지 않은 경우
    """
    if not x_api_key:
        logger.warning("[API_KEY_AUTH] X-API-Key 헤더가 없습니다")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key가 필요합니다. X-API-Key 헤더를 포함해주세요.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # API Key 검증
    api_key_obj = api_key_service.validate_key(db=db, api_key=x_api_key)

    if not api_key_obj:
        logger.warning("[API_KEY_AUTH] 유효하지 않은 API Key입니다")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API Key입니다.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Agent 권한 체크 (agent_code가 제공된 경우)
    if agent_code:
        if not api_key_obj.has_agent_permission(agent_code):
            logger.warning(
                f"[API_KEY_AUTH] API Key가 {agent_code} agent에 대한 권한이 없습니다"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"이 API Key는 {agent_code} agent에 대한 접근 권한이 없습니다.",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    logger.debug(
        f"[API_KEY_AUTH] API Key 검증 성공: id={api_key_obj.id}, name={api_key_obj.name}, agent={agent_code or 'all'}"
    )
    return api_key_obj
