import logging
from typing import Any, Dict, List

from src.agents.components.search_agent.search_result_compressor_component import (
    SearchResultCompressorComponent,
)


class SearchAgentCompressionNode:
    """검색 결과 압축 노드 - 워크플로우 조정"""

    def __init__(self, config: Dict[str, Any] = None, logger: Any = None):
        self.config = config or {}
        self.logger = logger or logging.getLogger("search_agent_compression_node")
        # Component 사용
        self.compressor_component = SearchResultCompressorComponent(self.config)

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        output = state.get("search_agent_output")
        tool_results: List[Dict[str, Any]] = []
        if isinstance(output, dict) and isinstance(output.get("tool_results"), list):
            tool_results = output.get("tool_results")
        knowledge = state.get("knowledge")
        query = state.get("user_query")
        intent = state.get("intent")

        # Component 사용
        summary = await self.compressor_component.compress(
            tool_results=tool_results,
            knowledge=knowledge,
            user_context=state.get("user_context"),
            query=query,
            intent=intent,
        )
        return {
            "search_agent_output": {"summary": summary, "tool_results": tool_results}
        }

    async def run_for_langgraph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph용 검색 결과 압축"""
        try:
            query = state.get("user_query", "")
            user_context = state.get("user_context", {})
            unified_tool_results = state.get("unified_tool_results", [])

            # 통합된 도구 결과가 비어있으면 빈 요약 반환
            if not unified_tool_results:
                return {
                    "summary": "",
                }
            if 'error' in state:
                return {
                    "summary": state.get("error", ""),
                    "tool_results": [],
                    "unified_tool_results": []
                }

            # Component를 사용한 결과 압축
            summary = await self.compressor_component.compress(
                tool_results=unified_tool_results,
                knowledge=state.get("knowledge"),
                user_context=user_context,
                query=query,
                intent=state.get("intent"),
            )

            return {
                "summary": summary,
                "tool_results": state.get("tool_results", []),
                "unified_tool_results": state.get("unified_tool_results", []),
                "next_node": "save_stm_message"
            }

        except Exception as e:
            self.logger.error(f"[SEARCH_AGENT_COMPRESSION] 검색 결과 압축 실패: {e}")
            return {
                "summary": "",
                "tool_results": state.get("tool_results", []),
                "unified_tool_results": state.get("unified_tool_results", []),
                "error": str(e),
            }
