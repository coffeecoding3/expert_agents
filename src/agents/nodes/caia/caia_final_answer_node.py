import logging
from typing import Any, Dict

from langchain_core.messages import AIMessage

from src.agents.components.caia.caia_final_answer_component import (
    CAIAFinalAnswerComponent,
)
from src.orchestration.states.caia_state import CAIAAgentState


class FinalAnswerNode:
    """최종 답변 노드 - 워크플로우 조정"""

    def __init__(
        self,
        llm_manager=None,
        prompt_manager=None,
        config: Dict[str, Any] = None,
        logger: Any = None,
    ):
        self.llm_manager = llm_manager
        self.prompt_manager = prompt_manager
        self.config = config or {}
        self.logger = logger or logging.getLogger("agents.final_answer_node")
        # Component 사용
        self.final_answer_component = CAIAFinalAnswerComponent()

    async def run(self, state: CAIAAgentState) -> CAIAAgentState:
        """최종 답변 생성 - Component 사용"""
        self.logger.debug("[GRAPH][7/7] 최종 답변 생성을 시작합니다")

        # Component 사용
        result = await self.final_answer_component.generate_final_answer(state)

        if result.get("success"):
            return {"messages": result["messages"]}
        else:
            self.logger.error(
                f"[GRAPH][7/7] 최종 답변 생성 실패: {result.get('error')}"
            )
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ]
            }

    async def stream_run(self, state: Dict[str, Any]):
        """스트리밍 모드로 최종 답변 생성 - Component 사용"""
        self.logger.info("[GRAPH][7/7] 최종 답변 스트리밍을 시작합니다")

        # Component 사용
        async for result in self.final_answer_component.stream_final_answer(state):
            yield result
