"""
도구 실행을 담당하는 클래스
"""

import inspect
import logging
from typing import Any, Dict, List, Optional

from src.agents.components.common.tool_registry import ToolRegistry
from src.agents.components.search_agent.mcp_handler import MCPHandler
from src.schemas.raih_exceptions import (
    RAIHBusinessException,
    RAIHAuthorizationException,
)
from src.utils.timezone_utils import get_timestamp, get_current_time_in_timezone

logger = logging.getLogger("tool_executor")


class ToolExecutor:
    """도구 실행을 담당하는 클래스"""

    def __init__(self):
        self.logger = logger
        self.mcp_handler = MCPHandler()

        # 실행 가능한 실제 도구 인스턴스 풀을 준비
        self.tool_instances = ToolRegistry.get_tool_instances()
        self.tools_by_name: Dict[str, Any] = {}
        for inst in self.tool_instances:
            try:
                name = getattr(inst, "name", inst.__class__.__name__)
                self.tools_by_name[name] = inst
            except Exception:
                continue

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

        # get_events 도구의 경우 날짜 파라미터를 현재 날짜로 명시적으로 설정
        if tool_name == "get_events":
            current_time = get_current_time_in_timezone()
            today = current_time.strftime("%Y-%m-%d")
            today_start = f"{today}T00:00:00"
            today_end = f"{today}T23:59:59"

            # 날짜 관련 파라미터가 없거나 잘못된 경우 현재 날짜로 설정(방어로직)
            if (
                not fixed.get("date")
                and not fixed.get("start_date_time")
                and not fixed.get("end_date_time")
            ):
                fixed["date"] = today
            else:
                # start_date_time과 end_date_time 파라미터 검증 및 수정 (안전장치)
                if fixed.get("start_date_time"):
                    if not fixed.get("start_date_time").startswith(today):
                        fixed["start_date_time"] = today_start

                if fixed.get("end_date_time"):
                    if not fixed.get("end_date_time").startswith(today):
                        fixed["end_date_time"] = today_end

                # date 파라미터도 검증 (안전장치)
                if fixed.get("date") and fixed.get("date") != today:
                    fixed["date"] = today

            # subject 파라미터가 없으면 쿼리에서 추출하여 설정
            if not fixed.get("subject") and query:
                # 간단한 키워드 추출 (실제로는 더 정교한 추출 로직이 필요할 수 있음)
                fixed["subject"] = query

        return fixed

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
                return True

        # 의도 분석 결과가 있는 경우 확인
        if user_context and user_context.get("intent"):
            intent = user_context.get("intent", "").lower()
            if "employee" in intent or "user" in intent or "person" in intent:
                return True

        return False

    async def execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        query: str,
        user_context: Optional[Dict[str, Any]] = None,
        available_tools_meta: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """도구 실행"""
        # 파라미터 정규화
        normalized_args = self.normalize_args(tool_name, args, query)

        # MCP 도구인 경우 SSO ID 추가
        if tool_name in [
            "get_events",
            "get_mails",
            "send_mail",
            "retrieve_personal_knowledge",
            "get_employee_infos_from_human_question",
        ]:
            if user_context and "sso_id" in user_context:
                normalized_args["sso_id"] = user_context["sso_id"]

        # MCP 도구인지 확인
        mcp_tool_info = None
        if available_tools_meta:
            mcp_tool_info = self.mcp_handler.is_mcp_tool(
                tool_name, available_tools_meta
            )

        if mcp_tool_info:
            # MCP 도구 실행 (통일된 서비스 사용)
            try:
                from src.capabilities.mcp_service import mcp_service
                from src.utils.config_utils import ConfigUtils

                # sso_id 추출
                sso_id = user_context.get("sso_id") if user_context else None

                return await mcp_service.call_mcp_tool_with_validation(
                    tool_name=tool_name,
                    client_name=mcp_tool_info.get("client", "lgenie"),
                    args=normalized_args,
                    sso_id=sso_id,
                )

            except Exception as e:
                self.logger.error(
                    f"[TOOL_EXECUTOR] MCP 도구 {tool_name} 실행 실패: {e}"
                )
                return None

        # 일반 도구 실행
        tool_inst = self.tools_by_name.get(tool_name)
        if not tool_inst:
            self.logger.warning(
                "[TOOL_EXECUTOR] %s 일반 도구를 찾을 수 없습니다", tool_name
            )
            return None

        try:
            # Tool 실행 시간 측정 시작
            tool_start_time = get_timestamp()
            result = await self._run_tool(
                tool_inst=tool_inst,
                tool_name=tool_name,
                args=normalized_args,
                query=query,
            )

            tool_duration = get_timestamp() - tool_start_time

            # tool 실행 결과 schema
            return {
                "tool": tool_name,
                "search_query": query,
                "parameters": normalized_args,
                "result": result,
                "duration": tool_duration,
            }

        except Exception as e:
            tool_duration = (
                get_timestamp() - tool_start_time
                if "tool_start_time" in locals()
                else 0.0
            )
            self.logger.error(f"[TOOL_EXECUTOR] {tool_name} 도구 실행 실패: {e}")
            return None

    async def _run_tool(
        self,
        tool_inst: Any,
        tool_name: str,
        args: Dict[str, Any],
        query: str,
    ) -> Any:
        """도구별 시그니처 차이를 최대한 유연하게 처리하여 실행"""
        run_fn = getattr(tool_inst, "run")
        sig = None
        try:
            sig = inspect.signature(run_fn)
        except Exception:
            sig = None

        # 특수 처리: web_search(query)
        if tool_name == "web_search":
            return await run_fn(args.get("query", query))

        # 단일 인자 도구: tool_input 또는 단일 프리미티브
        if sig is not None:
            params = [
                p
                for p in sig.parameters.values()
                if p.kind
                in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            ]
            if len(params) == 1:
                # 우선순위: prompt > query > 전체 args dict
                single = args.get("prompt") or args.get("query") or args
                return await run_fn(single)

        # 명시적 키워드 인자 시도
        try:
            return await run_fn(**args)
        except TypeError:
            # 최종 폴백: dict 한 방에 전달
            return await run_fn(args)
