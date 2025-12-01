"""
Base STM Message Node

모든 에이전트의 STM 메시지 저장 노드의 기본 클래스
공통 로직을 추출하여 중복을 제거합니다.
"""

from abc import ABC, abstractmethod
from logging import getLogger
from typing import Any, Callable, Dict

from src.agents.tools.common.stm_storage_tool import STMStorageTool

logger = getLogger("agents.base_stm_message_node")


class BaseSTMMessageNode(ABC):
    """STM 메시지 저장 노드의 기본 클래스"""

    def __init__(
        self,
        memory_manager: Any,
        logger: Any,
        get_agent_id: Callable[[Dict[str, Any]], int],
    ):
        """
        초기화

        Args:
            memory_manager: 메모리 매니저
            logger: 로거 인스턴스
            get_agent_id: 에이전트 ID 조회 함수
        """
        self.memory_manager = memory_manager
        self.logger = logger or getLogger("agents.base_stm_message_node")
        self.get_agent_id = get_agent_id
        # Tool 사용
        try:
            self.stm_storage_tool = STMStorageTool(memory_manager)
        except Exception as e:
            self.logger.error(
                f"[BASE_STM_NODE] STMStorageTool 초기화 실패: {e}", exc_info=True
            )
            raise

    async def save_stm_message(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        현재 대화를 STM에 저장합니다 - Tool 사용

        Args:
            state: 현재 상태

        Returns:
            빈 딕셔너리 (상태 변경 없음)
        """
        try:
            # Agent별로 tool_input 준비
            tool_input = self._prepare_tool_input(state)

            if not tool_input:
                self.logger.warning("[GRAPH] tool_input 준비 실패")
                return {}

            result = await self.stm_storage_tool.run(tool_input)

            if result.get("success"):
                self.logger.info("[GRAPH] 대화 메시지 저장이 완료되었습니다")
            else:
                self.logger.warning(
                    f"[GRAPH] 대화 메시지 저장 실패: {result.get('error')}"
                )

            return {}
        except Exception as e:
            self.logger.error(f"[GRAPH] 대화 메시지 저장 중 오류: {e}")
            return {}

    @abstractmethod
    def _prepare_tool_input(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Agent별로 state에서 tool_input을 준비합니다.

        Args:
            state: 현재 상태

        Returns:
            tool_input 딕셔너리
        """
        pass
