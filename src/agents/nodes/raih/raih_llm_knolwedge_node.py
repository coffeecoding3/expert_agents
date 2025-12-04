"""
RAIH LLM Knowledge Node
"""

from logging import getLogger
from typing import Any, Dict, List, Optional

from src.orchestration.states.raih_state import RAIHAgentState
from src.capabilities.mcp_service import mcp_service
from langchain_core.messages import AIMessage
from src.prompts.prompt_manager import prompt_manager
from src.schemas.raih_exceptions import (
    RAIHBusinessException,
    RAIHAuthorizationException,
)
from src.utils.config_utils import ConfigUtils

logger = getLogger("agents.raih_llm_knowledge_node")


# ... existing code ...
class RAIHLLMKnowledgeNode:
    """의도 분류 결과가 특정 카테고리일 때, 카테고리별 프롬프트로 LLM을 호출해 결과를 반환하는 노드"""

    def __init__(self, logger: Any, llm_config: Dict[str, Any]) -> None:
        """
        Args:
            logger: 로거
            llm_config: LLMNode 설정 (provider, model, temperature, max_tokens 등)
        """
        self.logger = logger
        self.llm_config = llm_config
        # LLMNode는 외부에서 제공되는 공용 LLM 매니저를 사용
        from src.agents.nodes.common.llm_node import (
            LLMNode,
        )  # 지역 import로 순환 참조 최소화

        self.llm = LLMNode(name="raih_llm_knowledge", config=self.llm_config)

    async def execute(self, state: RAIHAgentState):
        """
        비 분기 프롬프트 적용 시 해당 노드
        사내 조회 + llm
        """

        try:
            user_id = 0

            if state and isinstance(state, dict):
                user_id = state.get("user_id")

            if user_id:
                # user_id(숫자)를 sso_id(문자열)로 변환
                from src.apps.api.user.user_service import user_auth_service

                sso_id = user_auth_service.get_sso_id_from_user_id(user_id)

                if state.get("intent") == "general_question":
                    return await self._process_general_question(state)
                else:
                    return await self._process_corporate_knowledge(state, sso_id)

        except (RAIHBusinessException, RAIHAuthorizationException) as e:
            self.logger.error("[LLMKnowledge] execution failed: %s", e, exc_info=True)
            raise e

        except Exception as e:
            self.logger.error("[LLMKnowledge] execution failed: %s", e, exc_info=True)
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ],
                "error": str(e),
            }

    def _build_context(self, result_content: Dict[str, Any]):
        context_list = [
            f"title: {link['custom_title']}, context: {link['context']}\n"
            for link in result_content["documents"]
        ]
        return "\n\n".join(context_list)

    async def _process_general_question(self, state) -> Dict[str, Any]:
        messages = self._build_messages(state=state)
        llm_result = await self.llm.process({"messages": messages})

        return {
            "messages": [AIMessage(content=llm_result.get("content", ""))],
            "llm_knowledge_output": llm_result.get("content", ""),
        }

    async def _process_corporate_knowledge(self, state, sso_id) -> Dict[str, Any]:
        system_codes = ConfigUtils.get_raih_system_codes()
        call_tool_result = await mcp_service.call_mcp_tool_with_validation(
            client_name="lgenie",
            tool_name="retrieve_coporate_knowledge",
            args={
                "query": state["user_query"],
                "system_codes": system_codes,
                "top_k": 5,
            },
            sso_id=sso_id,
        )

        context = self._build_context(call_tool_result["result"])
        messages = self._build_messages(state=state, context=context)
        llm_result = await self.llm.process({"messages": messages})

        if llm_result.get("type") == "error":
            self.logger.error("[LLMKnowledge]LLM error: %s", llm_result.get("error"))
            return {
                "messages": [AIMessage(content=llm_result.get("error"))],
                "error": str(llm_result.get("error")),
            }

        return {
            "messages": [AIMessage(content=llm_result.get("content", ""))],
            "llm_knowledge_output": llm_result.get("content", ""),
        }

    def _build_messages(
        self, state: RAIHAgentState, context: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """카테고리별 시스템 프롬프트와 사용자 질의를 조합하여 메시지 생성"""

        user_query = state["user_query"]
        guidance = "한국어로 간결하지만 충분히 구체적으로 작성하고, 필요한 경우 표나 리스트로 구조화하세요. "

        # rag 중에서도 이슈 조회o(rag_issue), 이슈 조회x(rag_general) 내용 분리
        if state.get("intent") == "general_question":
            prompt_template = "raih/raih_general_question_v1.j2"
        elif "이슈" in user_query:
            prompt_template = "raih/raih_rag_issue_v1.j2"
        else:
            prompt_template = "raih/raih_rag_general_v1.j2"

        template_data = {
            "user_query": user_query,
            "chat_history": state["user_context"]["recent_messages"],
        }
        if prompt_template != "raih/raih_general_question_v1.j2":
            template_data["context"] = context

        rendered = prompt_manager.render_template(prompt_template, template_data)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": rendered},
            {"role": "system", "content": guidance},
            {"role": "user", "content": user_query},
        ]
        return messages
