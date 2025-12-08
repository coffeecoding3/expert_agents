"""
LexAI Response Handler

LexAI 에이전트 전용 응답 처리기 (JSON 응답)
"""

import json
from logging import getLogger
from typing import Any, AsyncGenerator, Dict, List

from src.orchestration.common.agent_interface import AgentResponseHandler

logger = getLogger("lexai_response_handler")


class LexAIResponseHandler(AgentResponseHandler):
    """LexAI 에이전트 전용 응답 처리기 (JSON 응답, SSE 없음)"""

    def __init__(self, logger=None):
        self.logger = logger or getLogger("lexai_response_handler")
        self.handled_nodes = [
            "generate_search_query",
            "search_corporate_knowledge",
            "generate_advice",
        ]
        # 최종 결과를 저장할 딕셔너리
        self.final_result: Dict[str, Any] = {}

    async def handle_response(
        self, node_name: str, node_output: Any
    ) -> AsyncGenerator[str, None]:
        """
        LexAI 전용 응답 처리 (JSON 수집)

        Note: LexAI는 SSE 스트리밍을 사용하지 않으므로 빈 제너레이터를 반환합니다.
        실제 JSON 응답은 router에서 final_result를 사용하여 생성합니다.

        Args:
            node_name: 노드 이름
            node_output: 노드 출력

        Yields:
            str: 빈 문자열 (SSE 스트리밍 사용 안 함)
        """
        if self.logger:
            self.logger.debug(f"[LEXAI_RESPONSE_HANDLER] 노드 '{node_name}' 처리 중")

        # 노드별 결과 저장
        if node_name == "generate_search_query":
            self.final_result["search_query"] = node_output.get("search_query")
        elif node_name == "search_corporate_knowledge":
            self.final_result["corporate_knowledge"] = node_output.get(
                "corporate_knowledge"
            )
        elif node_name == "generate_advice":
            self.final_result["advice"] = node_output.get("advice")
            # 메시지도 저장
            if "messages" in node_output:
                self.final_result["messages"] = node_output.get("messages")

        # SSE 스트리밍을 사용하지 않으므로 빈 제너레이터 반환
        # (yield가 없으면 빈 제너레이터가 됨)

    def get_handled_nodes(self) -> List[str]:
        """처리 가능한 노드 목록 반환"""
        return self.handled_nodes

    def get_final_result(self) -> Dict[str, Any]:
        """
        수집된 최종 결과를 반환합니다.

        Returns:
            Dict[str, Any]: 최종 결과
        """
        return self.final_result.copy()

    def reset(self):
        """결과를 초기화합니다."""
        self.final_result = {}
