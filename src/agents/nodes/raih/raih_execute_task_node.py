"""
RAIH Exectue Task Node
"""

import re
from logging import getLogger
from typing import Any, Dict, List, Optional
from latex2sympy2 import latex2sympy

from src.orchestration.states.raih_state import RAIHAgentState
from src.capabilities.mcp_service import mcp_service
from langchain_core.messages import AIMessage
from src.prompts.prompt_manager import prompt_manager
from src.schemas.raih_exceptions import RAIHBusinessException, RAIHAuthorizationException
from src.utils.config_utils import ConfigUtils

logger = getLogger("agents.raih_execute_task_node")

# ... existing code ...
class RAIHExecuteTaskNode:
    """의도 분류 결과가 특정 카테고리일 때, 카테고리별 프롬프트로 LLM을 호출해 결과를 반환하는 노드"""
    CATEGORY_PROMPTS = ['create_fmea', 'create_pdiagram', 'create_alt']
    # 정규식 패턴 상수 정의
    PATTERN_LATEX_BLOCK = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
    PATTERN_AF_T_APPROX = re.compile(r'AF_T\s*=\s*.*(?:\\approx|≈)\s*[\d.]+')
    PATTERN_FORMULA_EXTRACT = re.compile(r'=\s*(.*?)\s*(?:\\approx|≈)', re.DOTALL | re.IGNORECASE)
    PATTERN_EXP_FUNC = re.compile(r'\\exp\\left\[(.*)\\right\]')
    PATTERN_APPROX_VAL = r'(\\approx\s*[\d.]+)'
    PATTERN_EXP_VAL = r"(\\exp\()([0-9.]+)(\))"
    PATTERN_APPROX_VAL2 = r'≈\s*([\d.]+)'

    def __init__(self, logger: Any, llm_config: Dict[str, Any]) -> None:
        """
        Args:
            logger: 로거
            llm_config: LLMNode 설정 (provider, model, temperature, max_tokens 등)
        """
        self.logger = logger
        self.llm_config = llm_config
        # LLMNode는 외부에서 제공되는 공용 LLM 매니저를 사용
        from src.agents.nodes.common.llm_node import LLMNode  # 지역 import로 순환 참조 최소화

        self.llm = LLMNode(name="raih_execute_task",
                           config=self.llm_config)

    async def execute(self, state: RAIHAgentState) -> Dict[str, Any]:
        """
        카테고리별 프롬프트를 적용하여 LLM 호출 후 결과를 반환
        """
        intent = state.get("intent") or {}
        if intent not in self.CATEGORY_PROMPTS:
            msg = f"Unsupported category: {intent}"
            self.logger.warning("[ExecuteTask] %s", msg)
            return {"error": msg}

        try:
            user_id = 0
            sso_id = None

            if state and isinstance(state, dict):
                user_id = state.get("user_id")

            if user_id:
                # user_id(숫자)를 sso_id(문자열)로 변환
                from src.apps.api.user.user_service import user_auth_service
                sso_id = user_auth_service.get_sso_id_from_user_id(user_id)

            return await self._process(state, sso_id)

        except (RAIHBusinessException, RAIHAuthorizationException) as e:
            self.logger.error("[ExecuteTask] execution failed: %s", e, exc_info=True)
            raise e

        except Exception as e:
            self.logger.error("[ExecuteTask] execution failed: %s", e, exc_info=True)
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")],
                "error": str(e)
            }

    def _build_context(self, result_content: Dict[str, Any]):
        context_list = [
            f"title: {link['custom_title']}, context: {link['context']}\n"
            for link in result_content['documents']
        ]
        return "\n\n".join(context_list)

    def _build_messages(self, state: RAIHAgentState, intent: str, context: str) -> List[Dict[str, str]]:
        """카테고리별 시스템 프롬프트와 사용자 질의를 조합하여 메시지 생성"""
        if intent == 'create_fmea':
            prompt_template="raih/raih_create_fmea.j2"
        elif intent == 'create_alt':
            prompt_template="raih/raih_create_alt.j2"
        else:
            prompt_template="raih/raih_create_pdiagram.j2"

        user_query = state["user_query"]
        guidance = (
            "한국어로 간결하지만 충분히 구체적으로 작성하고, 필요한 경우 표나 리스트로 구조화하세요. "
            "가정이 필요하면 명시하고, 불확실성이나 추가 필요 정보도 마지막에 정리하세요."
        )

        rendered = prompt_manager.render_template(
            prompt_template,
            {
                "user_query": user_query,
                "context": context,
                "chat_history": state["user_context"]["recent_messages"]
            }
        )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": rendered},
            {"role": "system", "content": guidance},
            {"role": "user", "content": user_query},
        ]
        return messages

    async def _process(self, state, sso_id) -> Dict[str, Any]:
        system_codes = ConfigUtils.get_raih_system_codes()
        call_tool_result = await mcp_service.call_mcp_tool_with_validation(
            client_name="lgenie",
            tool_name="retrieve_coporate_knowledge",
            args={
                "query": state["user_query"],
                "system_codes": system_codes,
                "top_k": 5
            },
            sso_id=sso_id
        )

        context = self._build_context(call_tool_result["result"])
        messages = self._build_messages(state=state, intent=state["intent"], context=context)
        llm_result = await self.llm.process({"messages": messages})

        content = llm_result.get('content')
        if content:
            updated_content = self._calculate_and_update_latex_string(content)
            if updated_content:
                llm_result['content'] = updated_content

        if llm_result.get("type") == "error":
            self.logger.error("[LLMKnowledge]LLM error: %s", llm_result.get("error"))
            return {
                "messages": [AIMessage(content=llm_result.get("error"))],
                "error": str(llm_result.get("error"))
            }

        return {
            "messages": [AIMessage(content=llm_result.get("content", ""))],
            "llm_knowledge_output": llm_result.get("content", ""),
        }

    def _extract_latex_equations(self, latex_content: str) -> Optional[str]:
        """
        텍스트에서 이중 달러 기호($$)로 묶인 모든 LaTeX 수식을 추출합니다.
        """
        equations = self.PATTERN_LATEX_BLOCK.findall(latex_content)
        af_t_equations = [eq.strip() for eq in equations if 'AF_T' in eq]

        self.logger.info(f"[Latex equations] extracted latex equations: {af_t_equations}")
        if not af_t_equations:
            self.logger.info("[Latex equations] af_t_equations is empty")
            return None

        for item in af_t_equations:
            if self.PATTERN_AF_T_APPROX.search(item):
                self.logger.info(f"[Latex equations] extracted equation result: {item.strip()}")
                return item.strip()

        return None

    def _calculate_and_update_latex_string(self, llm_content: str) -> Optional[str]:
        """
        LaTeX 형식의 수식 문자열을 파싱하여 계산하고,
        기존 문자열의 결과값을 업데이트합니다.
        """
        latex_string = self._extract_latex_equations(llm_content)
        self.logger.info(f"[Latex equation] extracted equation: {latex_string}")

        if latex_string is None:
            return llm_content

        match_formula = self.PATTERN_FORMULA_EXTRACT.search(latex_string)
        self.logger.info(f"[Latex equation] match_formula: {match_formula}")

        if not match_formula:
            self.logger.error("[Latex equation] 수식 부분을 추출할 수 없습니다. 수식 문자열의 형식을 확인하세요.")
            return None

        formula_only_latex = match_formula.group(1).strip()
        if "=" in formula_only_latex:
            formula_only_latex = formula_only_latex.split("=")[0]

        self.logger.info(f"[Latex equation] formula_only_latex: {formula_only_latex}")

        match_value = self.PATTERN_EXP_FUNC.search(formula_only_latex)

        try:
            if not match_value:
                return self._process_simple_calculation(llm_content, formula_only_latex)
            else:
                return self._process_exp_calculation(llm_content, formula_only_latex, match_value)

        except Exception as e:
            self.logger.error(f"[Latex equation] 파싱 또는 계산 중 오류 발생: {e}")
            return None

    def _process_simple_calculation(self, llm_content: str, formula: str) -> str:
        """exp() 수식이 없는 단순 계산 처리"""
        self.logger.info("[Latex equation] exp() 수식 미존재")

        sympy_expr = latex2sympy(formula)
        calculated_expr = sympy_expr.evalf(5)
        self.logger.info(f"[Latex equation] calculated_expr: {calculated_expr}")

        new_result_str = rf"\\approx {calculated_expr}"

        updated_latex_string = re.sub(
            self.PATTERN_APPROX_VAL,
            new_result_str,
            llm_content,
            count=1
        )
        self.logger.info(f"[Latex equation] updated_latex_string(sub value) : {updated_latex_string}")
        return updated_latex_string

    def _process_exp_calculation(self, llm_content: str, formula: str, match_value: re.Match) -> str:
        """exp() 수식이 포함된 복합 계산 처리"""
        self.logger.info("[Latex equation] exp() 수식 존재")
        formula_to_calculate = match_value.group(1).strip()

        sympy_val = latex2sympy(formula_to_calculate)
        sympy_expr = latex2sympy(formula)

        calculated_expr = sympy_expr.evalf(5)
        calculated_value = sympy_val.evalf(5)

        self.logger.info(f"[Latex equation] calculated_expr: {calculated_expr}")
        self.logger.info(f"[Latex equation] calculated_value: {calculated_value}")

        new_result_str_main = rf"\\approx {calculated_expr}"
        new_result_str_main_2 = rf"≈ {calculated_expr}"
        new_result_str_exp = rf"\g<1>{calculated_value}\g<3>"

        # exp 내부 값 교체
        updated_latex_string = re.sub(
            self.PATTERN_EXP_VAL,
            new_result_str_exp,
            llm_content,
            count=1
        )
        self.logger.info(f"[Latex equation] updated_latex_string(main value) : \n{updated_latex_string}")

        # 'approx 값' 형태일 때
        updated_latex_string = re.sub(
            self.PATTERN_APPROX_VAL,
            new_result_str_main,
            updated_latex_string,
            count=1
        )

        # '≈ 값' 형태일 때
        updated_latex_string = re.sub(
            self.PATTERN_APPROX_VAL2,
            new_result_str_main_2,
            updated_latex_string,
        )
        self.logger.info(f"[Latex equation] updated_latex_string(sub value) : \n{updated_latex_string}")

        return updated_latex_string
