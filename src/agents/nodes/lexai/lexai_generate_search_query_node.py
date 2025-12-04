"""
LexAI Generate Search Query Node

법령명과 개정 내용을 분석하여 사내 규정 검색을 위한 최적의 쿼리를 생성하는 노드
"""

from logging import getLogger
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from src.agents.nodes.common.llm_node import LLMNode
from src.orchestration.states.lexai_state import LexAIAgentState
from src.prompts.prompt_manager import prompt_manager

logger = getLogger("agents.lexai_generate_search_query_node")


class LexAIGenerateSearchQueryNode:
    """법령명과 개정 내용을 분석하여 검색 쿼리를 생성하는 노드"""

    def __init__(self, logger: Any, llm_config: Dict[str, Any]) -> None:
        """
        Args:
            logger: 로거
            llm_config: LLMNode 설정 (provider, model, temperature, max_tokens 등)
        """
        self.logger = logger or getLogger("lexai_generate_search_query_node")
        self.llm_config = llm_config
        self.llm = LLMNode(name="lexai_generate_search_query", config=self.llm_config)

    async def execute(self, state: LexAIAgentState) -> Dict[str, Any]:
        """
        법령명과 개정 내용을 분석하여 검색 쿼리를 생성합니다.

        Args:
            state: LexAIAgentState 객체

        Returns:
            Dict[str, Any]: 생성된 검색 쿼리를 포함한 상태 업데이트
        """
        self.logger.info("[LEXAI_GENERATE_SEARCH_QUERY] 검색 쿼리 생성 시작")

        try:
            # 상태에서 필요한 데이터 추출
            law_nm = state.get("law_nm") or state.get("user_query", "")
            contents = state.get("contents", [])

            if not law_nm:
                self.logger.warning("[LEXAI_GENERATE_SEARCH_QUERY] 법령명이 없습니다")
                return {
                    "search_query": law_nm,
                }

            # 법령 개정 내용 포맷팅
            law_revision_text = self._format_law_revision(contents)

            # LLM 메시지 생성
            messages = self._build_messages(
                law_nm=law_nm,
                law_revision_text=law_revision_text,
            )

            # LLM 호출
            llm_result = await self.llm.process({"messages": messages})

            if llm_result.get("type") == "error":
                self.logger.error(
                    "[LEXAI_GENERATE_SEARCH_QUERY] LLM error: %s",
                    llm_result.get("error"),
                )
                # 오류 시 법령명을 그대로 사용
                return {
                    "search_query": law_nm,
                }

            search_query = llm_result.get("content", "").strip()

            # LLM 응답에서 쿼리 추출 (JSON 형식일 수도 있음)
            if search_query.startswith("{") or search_query.startswith("["):
                try:
                    import json

                    parsed = json.loads(search_query)
                    # JSON인 경우 "query" 키에서 추출하거나 배열의 첫 번째 요소 사용
                    if isinstance(parsed, dict):
                        search_query = parsed.get("query", law_nm)
                    elif isinstance(parsed, list) and len(parsed) > 0:
                        search_query = (
                            parsed[0] if isinstance(parsed[0], str) else law_nm
                        )
                except json.JSONDecodeError:
                    # JSON 파싱 실패 시 그대로 사용
                    pass

            # 빈 쿼리인 경우 법령명 사용
            if not search_query:
                search_query = law_nm

            self.logger.info(
                f"[LEXAI_GENERATE_SEARCH_QUERY] 검색 쿼리 생성 완료: {search_query[:100]}..."
            )

            return {
                "search_query": search_query,
            }

        except Exception as e:
            self.logger.error(
                f"[LEXAI_GENERATE_SEARCH_QUERY] 쿼리 생성 실패: {e}", exc_info=True
            )
            # 오류 시 법령명을 그대로 사용
            return {
                "search_query": state.get("law_nm") or state.get("user_query", ""),
            }

    def _format_law_revision(self, contents: List[Dict[str, str]]) -> str:
        """법령 개정 내용을 텍스트로 포맷팅"""
        if not contents:
            return "개정 내용 없음"

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
        self, law_nm: str, law_revision_text: str
    ) -> List[Dict[str, str]]:
        """LLM 메시지 생성"""
        # 프롬프트 템플릿 사용
        prompt_template = "lexai/lexai_search_query_generation.j2"

        try:
            rendered = prompt_manager.render_template(
                prompt_template,
                {
                    "law_nm": law_nm,
                    "law_revision_text": law_revision_text,
                },
            )
        except Exception as e:
            # 프롬프트 템플릿이 없으면 기본 프롬프트 사용
            self.logger.warning(
                f"[LEXAI_GENERATE_SEARCH_QUERY] 프롬프트 템플릿을 찾을 수 없어 기본 프롬프트 사용: {e}"
            )
            rendered = self._get_default_prompt(law_nm, law_revision_text)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": rendered},
            {
                "role": "user",
                "content": f"법령 '{law_nm}'의 개정 내용을 분석하여 사내 규정 검색을 위한 최적의 검색 쿼리를 생성해주세요.",
            },
        ]
        return messages

    def _get_default_prompt(self, law_nm: str, law_revision_text: str) -> str:
        """기본 프롬프트 (템플릿이 없을 때 사용)"""
        return f"""당신은 법령 개정 분석 전문가입니다. 법령 개정 내용을 분석하여 사내 규정을 검색하기 위한 최적의 검색 쿼리를 생성해야 합니다.

## 법령 정보
법령명: {law_nm}

## 법령 개정 내용
{law_revision_text}

## 요구사항
1. 법령명과 개정 내용을 분석하세요.
2. 개정된 내용에서 핵심 키워드와 용어를 추출하세요.
3. 사내 규정 검색에 최적화된 검색 쿼리를 생성하세요.
4. 검색 쿼리는 법령명, 개정된 조항, 관련 용어 등을 포함해야 합니다.

## 출력 형식
검색 쿼리만 출력하세요. 추가 설명 없이 쿼리만 반환합니다.

예시:
- "산업안전보건기준 화재위험작업 용접방화포 성능인증"
- "굴착기계 운전자 유도 규정"
"""
