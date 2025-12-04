"""
LexAI Search Knowledge Node

MCP를 사용하여 법령명으로 사내지식을 검색하는 노드
"""

import json
from logging import getLogger
from typing import Any, Dict

from src.capabilities.mcp_service import mcp_service
from src.orchestration.states.lexai_state import LexAIAgentState
from src.utils.config_utils import ConfigUtils

logger = getLogger("agents.lexai_search_knowledge_node")


class LexAISearchKnowledgeNode:
    """법령명으로 사내지식을 검색하는 노드"""

    def __init__(self, logger: Any = None):
        """
        Args:
            logger: 로거
        """
        self.logger = logger or getLogger("lexai_search_knowledge_node")

    async def execute(self, state: LexAIAgentState) -> Dict[str, Any]:
        """
        법령명으로 사내지식을 검색합니다.

        Args:
            state: LexAIAgentState 객체

        Returns:
            Dict[str, Any]: 검색 결과를 포함한 상태 업데이트
        """
        self.logger.info("[LEXAI_SEARCH_KNOWLEDGE] 사내지식 검색 시작")

        try:
            # LLM이 생성한 검색 쿼리 사용 (없으면 법령명 사용)
            search_query = state.get("search_query")
            law_nm = state.get("law_nm") or state.get("user_query", "")

            if not search_query:
                search_query = law_nm
                self.logger.warning(
                    "[LEXAI_SEARCH_KNOWLEDGE] 검색 쿼리가 없어 법령명을 사용합니다"
                )

            if not search_query:
                self.logger.warning(
                    "[LEXAI_SEARCH_KNOWLEDGE] 검색 쿼리와 법령명이 모두 없어 검색을 건너뜁니다"
                )
                return {
                    "corporate_knowledge": {"documents": []},
                }

            # 기본 system_codes 사용 (필요시 ConfigUtils에서 가져올 수 있음)
            system_codes = ConfigUtils.get_lexai_hse_system_codes()

            self.logger.info(
                f"[LEXAI_SEARCH_KNOWLEDGE] 검색 쿼리 '{search_query[:100]}...'로 사내지식 검색 중..."
            )

            # MCP 도구 호출 전 input 로깅
            mcp_tool_input = {
                "query": search_query,  # LLM이 생성한 검색 쿼리 사용
                "system_codes": system_codes,
                "top_k": 10,  # 법령 분석을 위해 더 많은 결과 가져오기
            }
            self.logger.info(
                f"[LEXAI_SEARCH_KNOWLEDGE] MCP Tool Input (retrieve_coporate_knowledge):\n"
                f"{json.dumps(mcp_tool_input, ensure_ascii=False, indent=2)}"
            )

            # MCP 도구 호출 (user 인증 없이 호출)
            call_tool_result = await mcp_service.call_mcp_tool_with_validation(
                client_name="lgenie",
                tool_name="retrieve_coporate_knowledge",
                args=mcp_tool_input,
                sso_id=None,  # user 인증 없이 호출
            )

            # MCP 도구 호출 후 output 로깅
            self.logger.info(
                f"[LEXAI_SEARCH_KNOWLEDGE] MCP Tool Output (retrieve_coporate_knowledge):\n"
                f"{json.dumps(call_tool_result, ensure_ascii=False, indent=2)}"
            )

            result_content = call_tool_result.get("result", {})
            documents = result_content.get("documents", [])

            self.logger.info(
                f"[LEXAI_SEARCH_KNOWLEDGE] 사내지식 검색 완료: {len(documents)}개 문서 발견"
            )

            return {
                "corporate_knowledge": result_content,
            }

        except Exception as e:
            self.logger.error(
                f"[LEXAI_SEARCH_KNOWLEDGE] 사내지식 검색 실패: {e}", exc_info=True
            )
            return {
                "corporate_knowledge": {"documents": [], "error": str(e)},
            }
