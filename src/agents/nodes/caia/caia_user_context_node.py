"""
CAIA User Context Node

사용자 컨텍스트를 구성하는 전용 노드
"""

from logging import getLogger
from typing import Any, Dict

from src.agents.tools.caia.user_context_builder_tool import UserContextBuilderTool
from src.orchestration.states.caia_state import CAIAAgentState
from src.utils.log_collector import collector

logger = getLogger("agents.caia_user_context_node")


class CAIAUserContextNode:
    """CAIA 사용자 컨텍스트 구성 노드"""

    def __init__(
        self,
        memory_manager: Any,
        logger: Any,
        get_agent_id,
    ):
        """
        초기화

        Args:
            memory_manager: 메모리 매니저
            logger: 로거
            get_agent_id: 에이전트 ID 조회 함수
        """
        self.memory_manager = memory_manager
        self.logger = logger
        self.get_agent_id = get_agent_id
        # Tool 사용
        self.user_context_builder_tool = UserContextBuilderTool(memory_manager)

    async def build_user_context(self, state: CAIAAgentState) -> CAIAAgentState:
        """
        사용자 컨텍스트를 구성합니다 - Tool 사용

        Args:
            state: 현재 상태

        Returns:
            user_context가 추가된 상태
        """
        user_id = state.get("user_id")
        agent_id = self.get_agent_id(state)
        session_id = state.get("session_id")

        self.logger.info("[GRAPH][1/7] 사용자 컨텍스트를 구성합니다")

        try:
            # UserContextBuilderTool의 run 메서드 호출
            tool_input = {
                "user_id": user_id,
                "agent_id": agent_id,
                "session_id": session_id,
                "k_recent": 3,
                "semantic_limit": 10,
                "episodic_limit": 5,
                "procedural_limit": 3,
                "personal_limit": 10,
            }

            result = await self.user_context_builder_tool.run(tool_input)

            if result.get("success"):
                user_context = result.get("user_context", {})
            else:
                raise Exception(result.get("error", "사용자 컨텍스트 구성 실패"))

            self.logger.info("[GRAPH][1/7] 사용자 컨텍스트 구성이 완료되었습니다")
            self.logger.debug(
                "[GRAPH][1/7] build_user_context:end "
                "recent=%d ltm=%d semantic=%d episodic=%d procedural=%d",
                len(user_context.get("recent_messages", [])),
                len(user_context.get("long_term_memories", [])),
                len(user_context.get("semantic_memories", [])),
                len(user_context.get("episodic_memories", [])),
                len(user_context.get("procedural_memories", [])),
            )
            # collector.log("user_context", user_context)

            return {"user_context": user_context}

        except Exception as e:
            self.logger.error(f"[GRAPH][1/7] 사용자 컨텍스트 구성 중 오류: {e}")
            return {
                "user_context": {
                    "recent_messages": [],
                    "session_summary": None,
                    "semantic_memories": [],
                    "episodic_memories": [],
                    "procedural_memories": [],
                    "long_term_memories": "",
                }
            }
