"""
User Context Builder Tool
사용자 컨텍스트 구성 도구 - 사용자의 메모리와 대화 이력을 종합하여 컨텍스트 구성
"""

from logging import getLogger
from typing import Any, Dict

from src.agents.tools.base_tool import BaseTool

logger = getLogger("agents.tools.user_context_builder")


class UserContextBuilderTool(BaseTool):
    """사용자 컨텍스트 구성 도구 - 데이터베이스 인터페이스"""

    name = "user_context_builder"
    description = "사용자의 메모리와 대화 이력을 종합하여 컨텍스트를 구성합니다."

    def __init__(self, memory_manager: Any):
        """초기화"""
        self.memory_manager = memory_manager

    async def run(self, tool_input: Any) -> Dict[str, Any]:
        """사용자 컨텍스트 구성 실행"""
        # 입력 검증
        if not isinstance(tool_input, dict):
            return {"error": "tool_input must be a dictionary", "success": False}

        try:
            user_id = tool_input.get("user_id")
            agent_id = tool_input.get("agent_id", 1)
            session_id = tool_input.get("session_id")

            # 컨텍스트 구성 옵션
            k_recent = tool_input.get("k_recent", 3)
            semantic_limit = tool_input.get("semantic_limit", 10)
            episodic_limit = tool_input.get("episodic_limit", 5)
            procedural_limit = tool_input.get("procedural_limit", 3)
            personal_limit = tool_input.get("personal_limit", 10)

            if not user_id:
                return {"error": "user_id is required", "success": False}

            logger.info("[USER_CONTEXT_BUILDER] 사용자 컨텍스트를 구성합니다")

            # UserContextBuilder 컴포넌트 사용
            from src.agents.components.common.user_context_builder import (
                UserContextBuilder,
            )

            user_context_builder = UserContextBuilder(self.memory_manager)
            user_context = await user_context_builder.build_user_context(
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_id,
                k_recent=k_recent,
                semantic_limit=semantic_limit,
                episodic_limit=episodic_limit,
                procedural_limit=procedural_limit,
                personal_limit=personal_limit,
            )

            logger.debug("[USER_CONTEXT_BUILDER] 사용자 컨텍스트 구성이 완료되었습니다")
            logger.info(
                "[USER_CONTEXT_BUILDER] recent=%d semantic=%d episodic=%d procedural=%d",
                len(user_context.get("recent_messages", [])),
                len(user_context.get("semantic_memories", [])),
                len(user_context.get("episodic_memories", [])),
                len(user_context.get("procedural_memories", [])),
            )

            return {"success": True, "user_context": user_context}

        except Exception as e:
            logger.error(f"[USER_CONTEXT_BUILDER] 사용자 컨텍스트 구성 중 오류: {e}")
            return {
                "error": str(e),
                "success": False,
                "user_context": {
                    "recent_messages": [],
                    "session_summary": None,
                    "semantic_memories": [],
                    "episodic_memories": [],
                    "procedural_memories": [],
                    "long_term_memories": "",
                },
            }

    def _get_input_schema(self) -> Dict[str, Any]:
        """입력 스키마 정의"""
        return {
            "type": "object",
            "properties": {
                "user_id": {"type": "integer", "description": "사용자 ID"},
                "agent_id": {
                    "type": "integer",
                    "description": "에이전트 ID (기본값: 1)",
                },
                "session_id": {"type": "string", "description": "세션 ID"},
                "k_recent": {
                    "type": "integer",
                    "description": "최근 메시지 수 (기본값: 5)",
                },
                "semantic_limit": {
                    "type": "integer",
                    "description": "의미적 메모리 제한 (기본값: 10)",
                },
                "episodic_limit": {
                    "type": "integer",
                    "description": "경험적 메모리 제한 (기본값: 5)",
                },
                "procedural_limit": {
                    "type": "integer",
                    "description": "절차적 메모리 제한 (기본값: 3)",
                },
                "personal_limit": {
                    "type": "integer",
                    "description": "개인 정보 제한 (기본값: 10)",
                },
            },
            "required": ["user_id"],
        }

    def _get_output_schema(self) -> Dict[str, Any]:
        """출력 스키마 정의"""
        return {
            "type": "object",
            "properties": {
                "success": {"type": "boolean", "description": "구성 성공 여부"},
                "user_context": {
                    "type": "object",
                    "description": "구성된 사용자 컨텍스트",
                    "properties": {
                        "recent_messages": {"type": "array"},
                        "session_summary": {"type": "string"},
                        "semantic_memories": {"type": "array"},
                        "episodic_memories": {"type": "array"},
                        "procedural_memories": {"type": "array"},
                        "long_term_memories": {"type": "string"},
                    },
                },
                "error": {"type": "string", "description": "오류 메시지 (실패시)"},
            },
        }
