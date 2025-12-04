"""
Memory Router for Expert Agents Service

메모리 통계 및 프로바이더 정보 조회
"""

from logging import getLogger
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

logger = getLogger("memory")

# 메모리 라우터
memory_router = APIRouter(prefix="/memory", tags=["Memory"])


@memory_router.get("/stats/{user_id}")
async def get_memory_stats(user_id: int) -> Dict[str, Any]:
    """사용자 메모리 통계 조회"""
    try:
        from src.memory.memory_manager import memory_manager

        stats = memory_manager.get_memory_stats(user_id)
        logger.info(f"[MEMORY] Memory stats retrieved for user {user_id}")
        return {
            "user_id": user_id,
            "stats": stats,
            "provider_info": memory_manager.get_provider_info(),
        }
    except Exception as e:
        logger.error(f"[MEMORY] Failed to get memory stats for {user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@memory_router.get("/provider-info")
async def get_memory_provider_info() -> Dict[str, Any]:
    """메모리 프로바이더 정보 조회"""
    try:
        from src.memory.memory_manager import memory_manager

        logger.info("[MEMORY] Memory provider info requested")
        return memory_manager.get_provider_info()
    except Exception as e:
        logger.error(f"[MEMORY] Failed to get memory provider info: {e}")
        raise HTTPException(status_code=500, detail=str(e))
