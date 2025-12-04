"""
Update Memory Tool
대화 내용을 episodic, semantic, procedural 메모리로 구분하여 저장하는 도구
"""

from logging import getLogger
from typing import Any, Dict

from src.agents.tools.base_tool import BaseTool
from src.memory.memory_manager import memory_manager

logger = getLogger("agents.tools.memory")


class UpdateMemoryTool(BaseTool):
    """메모리 저장 도구 - 데이터베이스 인터페이스"""

    name = "update_memory"
    description = (
        "대화 내용을 episodic, semantic, procedural 메모리로 구분하여 저장합니다."
    )

    async def run(self, tool_input: Any) -> Dict[str, Any]:
        """메모리 저장 실행"""
        # 입력 검증
        if not isinstance(tool_input, dict):
            return {"error": "tool_input must be a dictionary", "success": False}

        try:
            user_id = int(tool_input.get("user_id"))
            agent_id = (
                int(tool_input.get("agent_id"))
                if tool_input.get("agent_id") is not None
                else 1
            )
            memory_type = str(
                tool_input.get("memory_type")
            )  # episodic, semantic, procedural
            category = tool_input.get("category")
            importance = float(tool_input.get("importance", 1.0))
            session_id = tool_input.get("session_id")

            if memory_type == "stm_message":
                user_message = str(tool_input.get("user_message", ""))
                ai_message = str(tool_input.get("ai_message", ""))
                content = f"User: {user_message}\nAI: {ai_message}"
                ok = await _maybe_async(
                    memory_manager.save_stm_message,
                    user_id=user_id,
                    content=content,
                    agent_id=agent_id,
                    session_id=session_id,
                )
                return {
                    "ok": ok,
                    "saved_type": "episodic",
                    "category": "stm_message",
                    "session_id": session_id,
                    "success": ok,
                }

            if memory_type == "stm_summary":
                summary = str(tool_input.get("summary", ""))
                ok = await _maybe_async(
                    memory_manager.save_stm_summary,
                    user_id=user_id,
                    summary=summary,
                    agent_id=agent_id,
                    session_id=session_id,
                )
                return {
                    "ok": ok,
                    "saved_type": "episodic",
                    "category": "session_summary",
                    "session_id": session_id,
                    "success": ok,
                }

            if memory_type == "ltm":
                content = str(tool_input.get("content", ""))
                categories = tool_input.get("categories") or (
                    [category] if category else None
                )
                # memory_type 입력이 없으면 semantic 기본
                ltm_type = str(tool_input.get("ltm_type", "semantic")).lower()
                ok = await _maybe_async(
                    memory_manager.save_ltm,
                    user_id=user_id,
                    content=content,
                    categories=categories,
                    agent_id=agent_id,
                    importance=importance,
                    memory_type=ltm_type,
                )
                return {
                    "ok": ok,
                    "saved_type": ltm_type,
                    "category": categories,
                    "success": ok,
                }

            if memory_type == "personal":
                content = str(tool_input.get("content", ""))
                ok = await _maybe_async(
                    memory_manager.save_personal_fact,
                    user_id=user_id,
                    content=content,
                    agent_id=agent_id,
                )
                return {
                    "ok": ok,
                    "saved_type": "semantic",
                    "category": "personal",
                    "success": ok,
                }

            # fallback: 기본은 STM 메시지로 저장 (Redis)
            user_message = str(tool_input.get("user_message", ""))
            ai_message = str(tool_input.get("ai_message", ""))
            content = f"User: {user_message}\nAI: {ai_message}"
            ok = await _maybe_async(
                memory_manager.save_stm_message,
                user_id=user_id,
                content=content,
                agent_id=agent_id,
                session_id=session_id,
            )
            return {
                "ok": ok,
                "saved_type": "episodic",
                "category": "stm_message",
                "session_id": session_id,
                "success": ok,
            }

        except Exception as e:
            logger.error(f"ConversationMemoryTool failed: {e}")
            return {"ok": False, "error": str(e), "success": False}


async def _maybe_async(func, **kwargs):
    result = func(**kwargs)
    if hasattr(result, "__await__"):
        return await result  # type: ignore[misc]
    return result
