"""
Agent Interface
표준화된 에이전트 인터페이스 정의
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from typing_extensions import Protocol


class AgentState(Protocol):
    """에이전트 상태 프로토콜"""

    user_query: str
    messages: List[Any]
    agent_id: int
    user_id: int
    session_id: str
    actual_user_id: str
    user_context: Dict[str, Any]
    intent: str


class AgentResponse(Protocol):
    """에이전트 응답 프로토콜"""

    content: str
    metadata: Optional[Dict[str, Any]]
    streaming: bool
    done: bool


class BaseAgentOrchestrator(ABC):
    """기본 에이전트 오케스트레이터 인터페이스"""

    @abstractmethod
    async def run(self, state: AgentState) -> Dict[str, Any]:
        """에이전트 실행"""
        pass

    @abstractmethod
    def get_agent_info(self) -> Dict[str, Any]:
        """에이전트 정보 반환"""
        pass

    @abstractmethod
    def get_supported_intents(self) -> List[str]:
        """지원하는 의도 목록 반환"""
        pass


class AgentResponseHandler(ABC):
    """에이전트 응답 처리기 인터페이스"""

    @abstractmethod
    async def handle_response(
        self, node_name: str, node_output: Any
    ) -> AsyncGenerator[str, None]:
        """에이전트 응답을 SSE로 변환"""
        pass

    @abstractmethod
    def get_handled_nodes(self) -> List[str]:
        """처리 가능한 노드 목록 반환"""
        pass


class StandardAgentResponseHandler(AgentResponseHandler):
    """표준 에이전트 응답 처리기"""

    # 내부 처리 노드 목록 (SSE 응답을 생성하지 않음)
    INTERNAL_PROCESSING_NODES = {
        "save_stm_message",
        "save_chat_message",
        "sync_lgenie",
        "extract_and_save_memory",
        "analyze_query",  # 의도 분석 노드
    }

    def __init__(self, logger=None):
        self.logger = logger
        self.handled_nodes = []

    def _is_internal_processing_node(self, node_name: str) -> bool:
        """내부 처리 노드인지 확인"""
        return node_name in self.INTERNAL_PROCESSING_NODES

    async def handle_response(
        self, node_name: str, node_output: Any
    ) -> AsyncGenerator[str, None]:
        """표준 응답 처리"""
        # 내부 처리 노드는 SSE 응답을 생성하지 않음
        if self._is_internal_processing_node(node_name):
            if self.logger:
                self.logger.debug(
                    f"[RESPONSE_HANDLER] 내부 처리 노드 '{node_name}' 필터링됨"
                )
            return

        from src.schemas.sse_response import SSEResponse, MessageResponse

        # sse_metadata가 있으면 우선 처리
        if isinstance(node_output, dict) and "sse_metadata" in node_output:
            sse_metadata = node_output["sse_metadata"]
            sse_type = sse_metadata.get("sse_type", "llm")
            event_data = sse_metadata.get("event_data", {})
            links = sse_metadata.get("links", [])
            images = sse_metadata.get("images", [])
            streaming = sse_metadata.get("streaming", True)

            # content 추출
            content = self._extract_content(node_output)

            if content:
                if streaming and sse_type == "llm":
                    # 문자 단위 스트리밍
                    for char in content:
                        yield await SSEResponse.create_llm(
                            token=char, done=False
                        ).send()
                        await asyncio.sleep(0.01)

                # 최종 완료 응답
                if sse_type == "llm":
                    yield await SSEResponse.create_llm(
                        token=content if not streaming else content,
                        done=True,
                        message_res=MessageResponse.from_parameters(
                            content=content,
                            role="assistant",
                            links=links,
                            images=images,
                            event_data=event_data,
                        ),
                    ).send()
                elif sse_type == "status":
                    yield await SSEResponse.create_status(
                        status=event_data.get("status", ""),
                        token=content,
                    ).send()
                else:
                    # 기본 LLM 타입으로 처리
                    yield await SSEResponse.create_llm(
                        token=content,
                        done=True,
                        message_res=MessageResponse.from_parameters(
                            content=content,
                            role="assistant",
                            links=links,
                            images=images,
                            event_data=event_data,
                        ),
                    ).send()
                return

        # 기본적으로 모든 출력을 문자열로 변환하여 스트리밍
        content = self._extract_content(node_output)

        if content:
            # 내용을 토큰 단위로 스트리밍
            for char in content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)

            # 최종 완료 응답
            yield await SSEResponse.create_llm(
                token=content,
                done=True,
                message_res={
                    "content": content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()
        else:
            # 내용이 없는 경우
            error_content = f"{node_name} 노드에서 응답을 생성할 수 없습니다."
            yield await SSEResponse.create_llm(
                token=error_content,
                done=True,
                message_res={
                    "content": error_content,
                    "role": "assistant",
                    "links": [],
                    "images": [],
                },
            ).send()

    def _extract_content(self, node_output: Any) -> str:
        """노드 출력에서 내용 추출"""
        if isinstance(node_output, dict):
            # 일반적인 키들에서 내용 추출
            for key in ["content", "summary", "result", "output", "response"]:
                if key in node_output and node_output[key]:
                    return str(node_output[key])

            # messages 배열에서 내용 추출
            if "messages" in node_output and node_output["messages"]:
                messages = node_output["messages"]
                if messages and len(messages) > 0:
                    last_message = messages[-1]
                    if hasattr(last_message, "content"):
                        return last_message.content
                    else:
                        return str(last_message)

            # user_query는 제외하고 딕셔너리를 문자열로 변환
            filtered_output = {
                k: v
                for k, v in node_output.items()
                if k not in ["user_query", "user_id", "session_id", "agent_id"]
            }
            if filtered_output:
                return str(filtered_output)
            else:
                return ""
        else:
            # 단순 타입인 경우
            return str(node_output) if node_output else ""

    def get_handled_nodes(self) -> List[str]:
        """모든 노드를 처리 가능"""
        return ["*"]  # 와일드카드로 모든 노드 처리


class OrchestrationRegistry:
    """오케스트레이션 컴포넌트 레지스트리

    에이전트별 오케스트레이터와 응답 처리기를 관리합니다.
    BaseAgent 레지스트리(src/agents/agent_registry.py)와는 별도로
    오케스트레이션 관련 컴포넌트만 관리합니다.
    """

    def __init__(self, logger=None):
        from logging import getLogger

        self.logger = logger or getLogger("orchestration_registry")
        self._orchestrators: Dict[str, BaseAgentOrchestrator] = {}
        self._response_handlers: Dict[str, AgentResponseHandler] = {}
        self._default_handler = StandardAgentResponseHandler()

    def register_orchestrator(
        self, agent_code: str, orchestrator: BaseAgentOrchestrator
    ):
        """오케스트레이터 등록"""
        self._orchestrators[agent_code] = orchestrator
        self.logger.info(
            f"[ORCHESTRATION_REGISTRY] {agent_code.upper()} 오케스트레이터 등록 완료"
        )

    def register_response_handler(self, agent_code: str, handler: AgentResponseHandler):
        """응답 처리기 등록"""
        self._response_handlers[agent_code] = handler
        self.logger.info(
            f"[ORCHESTRATION_REGISTRY] {agent_code.upper()} 응답 처리기 등록 완료"
        )

    def get_orchestrator(self, agent_code: str) -> Optional[BaseAgentOrchestrator]:
        """오케스트레이터 조회"""
        return self._orchestrators.get(agent_code)

    def get_response_handler(self, agent_code: str) -> AgentResponseHandler:
        """응답 처리기 조회 (기본값 포함)"""
        return self._response_handlers.get(agent_code, self._default_handler)

    def get_supported_agents(self) -> List[str]:
        """지원하는 에이전트 목록 반환"""
        return list(self._orchestrators.keys())


# 전역 오케스트레이션 레지스트리 인스턴스
orchestration_registry = OrchestrationRegistry()
