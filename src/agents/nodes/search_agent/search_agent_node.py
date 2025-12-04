import logging
from typing import Any, Dict

from src.utils.log_collector import collector


class SearchAgentNode:
    def __init__(self, runner: Any, logger: Any = None):
        self.runner = runner
        self.logger = logger or logging.getLogger("search_agent_node")

    async def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.info("[GRAPH][4/7] 검색 에이전트를 시작합니다")
        query = state.get("user_query")
        # query = state["messages"][-1].content
        intent = state.get("intent")
        user_context = state.get("user_context") or {}
        result = await self.runner.run(
            query=query, intent=intent, user_context=user_context
        )
        tool_results = result.get("tool_results") or []
        plan = result.get("plan") or []

        self.logger.info("[GRAPH][4/7] 검색 에이전트가 완료되었습니다")
        collector.log(
            "search_agent_output", {"tool_results": tool_results, "plan": plan}
        )

        return {"search_agent_output": {"tool_results": tool_results, "plan": plan}}
