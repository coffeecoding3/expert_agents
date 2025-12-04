"""
Base Router for Expert Agents Service

기본 헬스체크 및 서비스 상태 조회
"""

from logging import getLogger
from typing import Any, Dict

from fastapi import APIRouter

logger = getLogger("base")

# 기본 라우터
base_router = APIRouter(tags=["Base"])


@base_router.get("/health")
async def health_check() -> Dict[str, str]:
    """헬스체크 엔드포인트"""
    logger.info("[HEALTH] Health check requested")
    return {"status": "healthy", "service": "expert-agents"}


@base_router.get("/status")
async def get_status() -> Dict[str, Any]:
    """서비스 상태 조회"""
    logger.info("[STATUS] Status check requested")
    return {
        "status": "running",
        "version": "0.1.0",
        "components": {
            "orchestration": "active",
            "capabilities": "active",
            "memory": "active",
            "chat": "active",
        },
    }
