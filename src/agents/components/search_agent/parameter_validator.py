"""
파라미터 검증 및 정규화를 담당하는 클래스
"""

import logging
from typing import Any, Dict, List, Optional

from src.utils.mcp_utils import get_default_mcp_value, validate_mcp_tool_args

logger = logging.getLogger("parameter_validator")


class ParameterValidator:
    """파라미터 검증 및 정규화를 담당하는 클래스"""

    def __init__(self):
        self.logger = logger

    def normalize_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        query: str,
    ) -> Dict[str, Any]:
        """플래너 args → 실제 구현 시그니처에 맞게 보정"""
        fixed = dict(args)

        if "query" not in fixed:
            fixed["query"] = query

        if tool_name == "llm_knowledge":
            if not fixed.get("prompt"):
                fixed["prompt"] = query

        return fixed

    def validate_mcp_tool_args(
        self, tool_name: str, args: Dict[str, Any], input_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """MCP 도구의 input schema에 맞게 파라미터 검증 및 정규화"""
        return validate_mcp_tool_args(tool_name, args, input_schema)

    def is_employee_search_intent(
        self, query: str, user_context: Optional[Dict[str, Any]]
    ) -> bool:
        """사용자 검색 의도인지 판단"""
        if not query:
            return False

        # 사용자 검색 관련 키워드들
        employee_keywords = [
            "사람",
            "직원",
            "임직원",
            "사원",
            "직원정보",
            "사람찾기",
            "누구",
            "어떤사람",
            "부서",
            "팀",
            "조직",
            "소속",
            "직책",
            "이름",
            "사번",
            "이메일",
            "employee",
            "staff",
            "person",
            "who",
            "find",
            "search",
        ]

        # 쿼리를 소문자로 변환하여 키워드 검색
        query_lower = query.lower()

        # 키워드 매칭
        for keyword in employee_keywords:
            if keyword in query_lower:
                self.logger.debug(
                    f"[PARAMETER_VALIDATOR] 사용자 검색 의도 감지: '{keyword}' in '{query}'"
                )
                return True

        # 의도 분석 결과가 있는 경우 확인
        if user_context and user_context.get("intent"):
            intent = user_context.get("intent", "").lower()
            if "employee" in intent or "user" in intent or "person" in intent:
                self.logger.debug(
                    f"[PARAMETER_VALIDATOR] 사용자 검색 의도 감지: intent='{intent}'"
                )
                return True

        self.logger.debug(f"[PARAMETER_VALIDATOR] 사용자 검색 의도가 아님: '{query}'")
        return False

    def add_sso_id_to_mcp_tools(
        self,
        tool_name: str,
        args: Dict[str, Any],
        user_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """MCP 도구인 경우 SSO ID 추가"""
        mcp_tools = [
            "get_events",
            "get_mails",
            "send_mail",
            "get_employee_infos_from_human_question",
        ]

        if tool_name in mcp_tools and user_context and "sso_id" in user_context:
            args["sso_id"] = user_context["sso_id"]

        return args
