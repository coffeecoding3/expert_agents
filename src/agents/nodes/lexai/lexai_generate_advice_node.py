"""
LexAI Generate Advice Node

법령 개정 내용과 사내지식을 기반으로 LLM을 사용하여 규정 변경 조언을 생성하는 노드
"""

from logging import getLogger
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from src.agents.nodes.common.llm_node import LLMNode
from src.orchestration.states.lexai_state import LexAIAgentState
from src.prompts.prompt_manager import prompt_manager

logger = getLogger("agents.lexai_generate_advice_node")


class LexAIGenerateAdviceNode:
    """법령 개정 내용과 사내지식을 기반으로 규정 변경 조언을 생성하는 노드"""

    def __init__(self, logger: Any, llm_config: Dict[str, Any]) -> None:
        """
        Args:
            logger: 로거
            llm_config: LLMNode 설정 (provider, model, temperature, max_tokens 등)
        """
        self.logger = logger or getLogger("lexai_generate_advice_node")
        self.llm_config = llm_config
        self.llm = LLMNode(name="lexai_generate_advice", config=self.llm_config)

    async def execute(self, state: LexAIAgentState) -> Dict[str, Any]:
        """
        법령 개정 내용과 사내지식을 기반으로 규정 변경 조언을 생성합니다.

        Args:
            state: LexAIAgentState 객체

        Returns:
            Dict[str, Any]: 생성된 조언을 포함한 상태 업데이트
        """
        self.logger.info("[LEXAI_GENERATE_ADVICE] 규정 변경 조언 생성 시작")

        try:
            # 상태에서 필요한 데이터 추출
            law_nm = state.get("law_nm") or state.get("user_query", "")
            contents = state.get("contents", [])
            corporate_knowledge = state.get("corporate_knowledge", {})
            openapi_log_id = state.get("openapi_log_id", "")
            old_and_new_no = state.get("old_and_new_no", "")

            if not contents:
                self.logger.warning("[LEXAI_GENERATE_ADVICE] 법령 개정 내용이 없습니다")
                return {
                    "messages": [AIMessage(content="법령 개정 내용이 없습니다.")],
                    "advice": {"error": "법령 개정 내용이 없습니다."},
                }

            # 사내지식 검색 결과 포맷팅
            knowledge_context = self._format_corporate_knowledge(corporate_knowledge)

            # 법령 개정 내용 포맷팅
            law_revision_text = self._format_law_revision(contents)

            # LLM 메시지 생성
            messages = self._build_messages(
                law_nm=law_nm,
                law_revision_text=law_revision_text,
                knowledge_context=knowledge_context,
                openapi_log_id=openapi_log_id,
                old_and_new_no=old_and_new_no,
            )

            # LLM 호출
            llm_result = await self.llm.process({"messages": messages})

            if llm_result.get("type") == "error":
                self.logger.error(
                    "[LEXAI_GENERATE_ADVICE] LLM error: %s", llm_result.get("error")
                )
                return {
                    "messages": [
                        AIMessage(content=llm_result.get("error", "오류 발생"))
                    ],
                    "advice": {"error": str(llm_result.get("error"))},
                }

            advice_content = llm_result.get("content", "")

            self.logger.info("[LEXAI_GENERATE_ADVICE] 규정 변경 조언 생성 완료")

            return {
                "messages": [AIMessage(content=advice_content)],
                "advice": {
                    "content": advice_content,
                    "model": llm_result.get("model"),
                    "usage": llm_result.get("usage"),
                    "metadata": llm_result.get("metadata"),
                },
            }

        except Exception as e:
            self.logger.error(
                f"[LEXAI_GENERATE_ADVICE] 조언 생성 실패: {e}", exc_info=True
            )
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 조언 생성 중 오류가 발생했습니다.")
                ],
                "advice": {"error": str(e)},
            }

    def _format_corporate_knowledge(self, corporate_knowledge: Dict[str, Any]) -> str:
        """사내지식 검색 결과를 텍스트로 포맷팅"""
        if not corporate_knowledge:
            return "관련 사내 규정을 찾을 수 없습니다."

        documents = corporate_knowledge.get("documents", [])
        if not documents:
            return "관련 사내 규정을 찾을 수 없습니다."

        context_list = []
        for doc in documents:
            title = doc.get("custom_title", doc.get("title", "제목 없음"))
            context = doc.get("context", "")
            context_list.append(f"제목: {title}\n내용: {context}\n")

        return "\n\n".join(context_list)

    def _format_law_revision(self, contents: List[Dict[str, str]]) -> str:
        """법령 개정 내용을 텍스트로 포맷팅"""
        revision_list = []
        for content in contents:
            content_no = content.get("content_no", "")
            old_content = content.get("old_content", "")
            new_content = content.get("new_content", "")
            revision_list.append(
                f"[내용 {content_no}]\n"
                f"개정 전: {old_content}\n"
                f"개정 후: {new_content}\n"
            )
        return "\n".join(revision_list)

    def _build_messages(
        self,
        law_nm: str,
        law_revision_text: str,
        knowledge_context: str,
        openapi_log_id: str = "",
        old_and_new_no: str = "",
    ) -> List[Dict[str, str]]:
        """LLM 메시지 생성"""
        # 프롬프트 템플릿 사용 (나중에 lexai 전용 프롬프트 추가 가능)
        # 현재는 기본 프롬프트 사용
        prompt_template = "lexai/lexai_regulation_advice.j2"

        try:
            rendered = prompt_manager.render_template(
                prompt_template,
                {
                    "law_nm": law_nm,
                    "law_revision_text": law_revision_text,
                    "knowledge_context": knowledge_context,
                    "openapi_log_id": openapi_log_id,
                    "old_and_new_no": old_and_new_no,
                },
            )
        except Exception as e:
            # 프롬프트 템플릿이 없으면 기본 프롬프트 사용
            self.logger.warning(
                f"[LEXAI_GENERATE_ADVICE] 프롬프트 템플릿을 찾을 수 없어 기본 프롬프트 사용: {e}"
            )
            rendered = self._get_default_prompt(
                law_nm,
                law_revision_text,
                knowledge_context,
                openapi_log_id,
                old_and_new_no,
            )

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": rendered},
            {
                "role": "user",
                "content": f"법령 '{law_nm}'의 개정 내용을 분석하여 사내 규정 변경 조언을 생성해주세요.",
            },
        ]
        return messages

    def _get_default_prompt(
        self,
        law_nm: str,
        law_revision_text: str,
        knowledge_context: str,
        openapi_log_id: str = "",
        old_and_new_no: str = "",
    ) -> str:
        """기본 프롬프트 (템플릿이 없을 때 사용)"""
        return f"""당신은 법령 개정 분석 전문가입니다. 법령 개정 내용을 분석하여 사내 규정 변경 조언을 생성해야 합니다.

## 법령 정보
법령명: {law_nm}

## 법령 개정 내용
{law_revision_text}

## 관련 사내 규정
{knowledge_context}

## 요구사항
1. 법령 개정 내용을 분석하세요.
2. 관련 사내 규정을 확인하세요.
3. 변경이 필요한 사내 규정 부분을 식별하세요.
4. 구체적인 변경 조언을 생성하세요.

응답은 다음 JSON 형식으로 제공해주세요:
{{
  "openapi_log_id": "{openapi_log_id}",
  "old_and_new_no": "{old_and_new_no}",
  "details": [
    {{
      "center": "센터명",
      "category": "카테고리",
      "standard": "규정명",
      "content_no": "내용 번호",
      "before_lgss_content": "변경 전 LGSS 내용",
      "ai_review": "AI 검토 내용",
      "ai_suggestion": "AI 제안 사항",
      "suggetsion_accuracy": "정확도 (0-100)"
    }}
  ]
}}
"""
