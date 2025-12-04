"""
Search Execution Node
검색 도구 실행 노드
"""

import logging
from typing import Any, Dict

from src.agents.search_agent import SearchAgentWrapper
from src.schemas.raih_exceptions import (
    RAIHAuthorizationException,
    RAIHBusinessException,
)

logger = logging.getLogger("search_execution_node")


class SearchAgentExecutionNode:
    """검색 도구 실행 노드"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger("search_execution_node")
        # SearchAgentWrapper는 state에서 agent_id를 가져와서 동적으로 생성
        self._search_agent_cache = {}

    def _get_search_agent(self, agent_id: int = None, agent_code: str = None):
        """agent_id나 agent_code에 따라 SearchAgentWrapper를 가져오거나 생성"""
        cache_key = agent_code or f"agent_{agent_id}"
        if cache_key not in self._search_agent_cache:
            config = {}
            if agent_id:
                config["agent_id"] = agent_id
            if agent_code:
                config["agent_code"] = agent_code
            self._search_agent_cache[cache_key] = SearchAgentWrapper(config=config)
        return self._search_agent_cache[cache_key]

    async def run_for_langgraph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph용 검색 도구 실행"""
        self.logger.debug("[SEARCH_EXECUTION] 검색 도구 실행 시작")

        try:
            query = state.get("user_query", "")
            user_context = state.get("user_context", {})
            plan = state.get("plan", [])
            available_tools_meta = state.get("available_tools", [])

            # agent_id에 따라 agent_code 결정
            agent_id = state.get("agent_id")
            agent_code = "raih" if agent_id == 2 else "caia"
            search_agent = self._get_search_agent(
                agent_id=agent_id, agent_code=agent_code
            )

            # 계획이 비어있으면 빈 결과 반환
            if not plan:
                self.logger.info("[SEARCH_EXECUTION] 검색 계획이 비어있습니다")
                return {
                    "tool_results": [],
                    "unified_tool_results": [],
                }

            # 도구 실행
            tool_results = await search_agent._execute_plan(
                plan, query, user_context, available_tools_meta
            )

            # 도구 결과가 비어있으면 빈 결과 반환
            if not tool_results:
                self.logger.info("[SEARCH_EXECUTION] 도구 실행 결과가 비어있습니다")
                return {
                    "tool_results": [],
                    "unified_tool_results": [],
                }

            # 도구 결과를 통합 형식으로 변환
            unified_tool_results = await search_agent._convert_tool_results(
                tool_results, query, user_context
            )

            self.logger.debug(
                f"[SEARCH_EXECUTION] 검색 도구 실행 완료: {len(tool_results)}개 결과"
            )

            return {
                "tool_results": tool_results,
                "unified_tool_results": unified_tool_results,
            }

        except (RAIHBusinessException, RAIHAuthorizationException) as e:
            raise e

        except Exception as e:
            self.logger.error(f"[SEARCH_EXECUTION] 검색 도구 실행 실패: {e}")
            return {
                "tool_results": [],
                "unified_tool_results": [],
                "error": str(e),
            }
