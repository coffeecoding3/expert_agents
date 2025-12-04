"""
Workflow Manager V2
표준화된 워크플로우 실행 및 관리 담당
"""

import asyncio
from logging import getLogger
from typing import Any, AsyncGenerator, Dict

from src.orchestration.common.agent_interface import (
    OrchestrationRegistry,
    AgentResponseHandler,
)
from src.orchestration.states.caia_state import CAIAAgentState
from src.schemas.sse_response import SSEResponse

logger = getLogger("workflow_manager_v2")


class WorkflowManagerV2:
    """표준화된 워크플로우 매니저 - 모든 에이전트 지원"""

    def __init__(self, orchestration_registry: OrchestrationRegistry):
        self.orchestration_registry = orchestration_registry
        self.logger = logger

    async def execute_workflow(
        self, state: CAIAAgentState, agent_code: str = "caia"
    ) -> AsyncGenerator[str, None]:
        """워크플로우를 실행하고 SSE로 스트리밍합니다."""
        self.logger.info(f"[WORKFLOW_MANAGER_V2] 워크플로우 실행 시작: {agent_code}")

        try:
            # 에이전트별 오케스트레이터 가져오기
            orchestrator = self.orchestration_registry.get_orchestrator(agent_code)

            if orchestrator is None:
                self.logger.error(
                    f"{agent_code} 에이전트용 오케스트레이터를 찾을 수 없습니다."
                )
                error_response = await SSEResponse.create_error(
                    f"{agent_code} 에이전트를 찾을 수 없습니다."
                ).send()
                yield error_response
                return

            # 워크플로우 실행
            async for chunk in orchestrator.workflow.astream(state):
                # 각 노드의 출력을 SSE로 스트리밍
                for node_name, node_output in chunk.items():
                    if node_output:
                        async for response in self._create_node_output_response(
                            agent_code, node_name, node_output
                        ):
                            yield response

        except asyncio.CancelledError:
            self.logger.warning(
                "[WORKFLOW_MANAGER_V2] 워크플로우 실행이 취소되었습니다."
            )
            error_response = await SSEResponse.create_error(
                "워크플로우 실행이 취소되었습니다."
            ).send()
            yield error_response
        except Exception as e:
            self.logger.error(f"[WORKFLOW_MANAGER_V2] 워크플로우 실행 실패: {e}")
            error_response = await SSEResponse.create_error(
                f"워크플로우 실행 중 오류가 발생했습니다: {str(e)}"
            ).send()
            yield error_response

    async def _create_node_output_response(
        self, agent_code: str, node_name: str, node_output: Any
    ):
        """워크플로우 노드 출력을 SSE 응답으로 변환합니다."""
        # 에이전트별 응답 처리기 가져오기
        response_handler = self.orchestration_registry.get_response_handler(agent_code)

        # 응답 처리기로 처리
        async for response in response_handler.handle_response(node_name, node_output):
            yield response

    def register_agent(self, agent_code: str, orchestrator, response_handler=None):
        """새로운 에이전트 등록"""
        self.orchestration_registry.register_orchestrator(agent_code, orchestrator)

        if response_handler:
            self.orchestration_registry.register_response_handler(
                agent_code, response_handler
            )

        self.logger.info(f"[WORKFLOW_MANAGER_V2] {agent_code} 에이전트 등록 완료")

    def get_supported_agents(self) -> list:
        """지원하는 에이전트 목록 반환"""
        return self.orchestration_registry.get_supported_agents()

    def get_agent_info(self, agent_code: str) -> Dict[str, Any]:
        """에이전트 정보 조회"""
        orchestrator = self.orchestration_registry.get_orchestrator(agent_code)
        if orchestrator:
            return orchestrator.get_agent_info()
        return {}


class WorkflowManagerFactory:
    """워크플로우 매니저 팩토리"""

    @staticmethod
    def create_standard_manager() -> WorkflowManagerV2:
        """표준 워크플로우 매니저 생성"""
        from src.orchestration.caia.caia_orchestrator import CAIAOrchestrator
        from src.orchestration.caia.caia_response_handler import CAIAResponseHandler
        from src.orchestration.common.agent_interface import OrchestrationRegistry

        # 오케스트레이션 레지스트리 생성
        orchestration_registry = OrchestrationRegistry()

        # CAIA 에이전트 등록
        caia_orchestrator = CAIAOrchestrator()
        caia_response_handler = CAIAResponseHandler()

        orchestration_registry.register_orchestrator("caia", caia_orchestrator)
        orchestration_registry.register_response_handler("caia", caia_response_handler)

        # 워크플로우 매니저 생성
        workflow_manager = WorkflowManagerV2(orchestration_registry)

        logger.info("[WORKFLOW_MANAGER_FACTORY] 표준 워크플로우 매니저 생성 완료")
        return workflow_manager

    @staticmethod
    def create_custom_manager(
        custom_registry: OrchestrationRegistry,
    ) -> WorkflowManagerV2:
        """커스텀 워크플로우 매니저 생성"""
        return WorkflowManagerV2(custom_registry)
