"""
Base Orchestrator Interface
모든 에이전트가 공통으로 사용할 수 있는 오케스트레이터 인터페이스
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, Optional, Type

from langgraph.graph import StateGraph


class BaseOrchestrator(ABC):
    """
    모든 에이전트 오케스트레이터의 기본 인터페이스
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.workflow: Optional[StateGraph] = None

    @abstractmethod
    def build_workflow(self) -> StateGraph:
        """
        에이전트별 워크플로우를 구성합니다.

        Returns:
            StateGraph: 구성된 워크플로우
        """
        pass

    @abstractmethod
    async def run(self, state: Dict[str, Any]) -> None:
        """
        주어진 상태로 에이전트를 실행합니다.

        Args:
            state: 에이전트 상태 딕셔너리
        """
        pass

    @abstractmethod
    def get_state_schema(self) -> Type:
        """
        에이전트가 사용하는 상태 스키마를 반환합니다.

        Returns:
            Type: 상태 스키마 클래스
        """
        pass

    @abstractmethod
    def get_entry_point(self) -> str:
        """
        워크플로우의 진입점 노드명을 반환합니다.

        Returns:
            str: 진입점 노드명
        """
        pass

    def compile_workflow(self) -> None:
        """
        워크플로우를 컴파일합니다.
        """
        if not self.workflow:
            self.workflow = self.build_workflow()
            self.workflow = self.workflow.compile()

    def get_workflow(self) -> StateGraph:
        """
        컴파일된 워크플로우를 반환합니다.

        Returns:
            StateGraph: 컴파일된 워크플로우
        """
        if not self.workflow:
            self.compile_workflow()
        return self.workflow

    async def astream_sse(
        self,
        state: Dict[str, Any],
        response_handler: "AgentResponseHandler",  # type: ignore
    ) -> AsyncGenerator[str, None]:
        """
        워크플로우 실행과 SSE 변환을 통합한 스트리밍 메서드

        Args:
            state: 에이전트 상태 딕셔너리
            response_handler: SSE 응답 변환을 위한 핸들러

        Yields:
            str: SSE 형식의 응답 문자열
        """
        # 워크플로우가 컴파일되지 않았다면 컴파일
        if not self.workflow:
            self.compile_workflow()

        # 워크플로우 실행 및 SSE 변환
        async for chunk in self.workflow.astream(state):
            for node_name, node_output in chunk.items():
                if node_output:
                    async for sse_response in response_handler.handle_response(
                        node_name, node_output
                    ):
                        yield sse_response
