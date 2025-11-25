"""
Memory Candidate Extractor (3-depth)

세션 전체 내용으로부터 다음 3가지 관점(symantic, episodic, procedural)에서 메모리 후보를 추출하고,
각 관점 내에서 임의의 카테고리로 묶은 뒤, 항목별로 source(fact|inferred)를 표시합니다.
"""

from logging import getLogger
from typing import Any, Dict, List, Optional

from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser
from src.llm.interfaces import ChatMessage
from src.llm.interfaces.chat import MessageRole
from src.llm.manager import llm_manager
from src.prompts.prompt_manager import prompt_manager

logger = getLogger("agents.components.memory_candidate_extractor")


class MemoryCandidateExtractor:
    """Memory Candidate 추출기(3-depth)"""

    def __init__(self, *, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider or "openai"
        self.model = model

    async def extract_new(
        self, time: str, chat_history: List[Dict[str, str]], user_query: str = None
    ) -> str:

        try:
            prompt = prompt_manager.render_template(
                "caia/caia_memory_extractor_v2.j2",
                {"user_query": user_query, "chat_history": chat_history, "time": time},
            )

            messages = [
                ChatMessage(role=MessageRole.USER, content=prompt),
            ]

            response = await llm_manager.chat(
                messages=messages,
                provider=self.provider,
                model=self.model,
                temperature=0.0,
            )

            return response.content

        except Exception as e:
            logger.error(f"[MEMORY_EXTRACT] 메모리 후보 추출 실패: {e}")
            return "not memory"

    async def extract(
        self, session_content: str, user_query: str = None
    ) -> Dict[str, Any]:
        """사용자 질의에서만 3-단계 구조의 메모리 후보를 추출합니다.

        Args:
            session_content: 전체 세션 내용 (컨텍스트 참조용)
            user_query: 사용자의 최신 질의 (메모리 추출 대상)

        Returns structure:
        {
          "semantic": {"<category>": [{"content", "importance", "source"}, ...]},
          "episodic": { ... },
          "procedural": { ... }
        }
        """
        try:
            # 사용자 질의만 사용 (LLM 답변 제외)
            if not user_query:
                logger.warning(
                    "[MEMORY_EXTRACT] 메모리 후보 추출 실패: 사용자 질의 없음"
                )
                return {
                    "long_term_memory": {},
                    "symantic": {},
                    "episodic": {},
                    "procedural": {},
                }

            logger.info(f"[MEMORY_EXTRACT] 사용자 질의: {user_query}")
            logger.info(f"[MEMORY_EXTRACT] 세션 컨텍스트 길이: {len(session_content)}")

            query_to_extract = user_query

            prompt = prompt_manager.render_template(
                "caia/caia_memory_extractor.j2",
                {"user_query": query_to_extract, "session_content": session_content},
            )

            messages = [
                ChatMessage(role=MessageRole.USER, content=prompt),
            ]

            logger.info(f"[MEMORY_EXTRACT] LLM 호출 시작")
            response = await llm_manager.chat(
                messages=messages,
                provider=self.provider,
                model=self.model,
                temperature=0.0,
            )
            logger.info(f"[MEMORY_EXTRACT] LLM 응답 받음: {response.content[:200]}...")

            # LLMResponseJsonParser를 사용하여 안전하게 JSON 파싱
            fallback_response = {
                "long_term_memory": {},
            }
            parser = LLMResponseJsonParser(fallback_response=fallback_response)

            try:
                raw = parser.parse(response.content)
                logger.info(f"[MEMORY_EXTRACT] JSON 파싱 성공: {raw}")
            except Exception as e:
                logger.warning(f"[MEMORY_EXTRACT] 메모리 후보 추출 JSON 파싱 실패: {e}")
                logger.warning(f"[MEMORY_EXTRACT] 원본 응답: {response.content}")
                return fallback_response

            normalized = self._normalize_ltm(raw)
            logger.info(f"[MEMORY_EXTRACT] 정규화 완료: {normalized}")
            return normalized
        except Exception as e:
            logger.error(f"[MEMORY_EXTRACT] 메모리 후보 추출 실패: {e}")
            return {
                "long_term_memory": {},
            }

    def _normalize_ltm(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """LTM(Long Term Memory) 전용 정규화 메서드"""

        def norm_bucket(bucket: Any) -> Dict[str, List[Dict[str, Any]]]:
            result: Dict[str, List[Dict[str, Any]]] = {}
            if not isinstance(bucket, dict):
                return result
            for category, items in bucket.items():
                cat = str(category).strip()
                if not isinstance(items, list):
                    continue
                normalized_items: List[Dict[str, Any]] = []
                seen_contents = set()  # 중복 제거를 위한 집합

                for it in items:
                    if not isinstance(it, dict):
                        continue
                    content = str(it.get("content", "")).strip()
                    if not content:
                        continue

                    # 중복 제거: 비슷한 내용이 이미 있는지 확인
                    content_key = content.lower().strip()
                    if content_key in seen_contents:
                        continue
                    seen_contents.add(content_key)

                    importance_raw = it.get("importance", 0.5)
                    try:
                        importance = max(0.0, min(1.0, float(importance_raw)))
                    except Exception:
                        importance = 0.5
                    source = str(it.get("source", "inferred")).strip().lower()
                    source = "fact" if source == "fact" else "inferred"
                    normalized_items.append(
                        {
                            "content": content,
                            "importance": importance,
                            "source": source,
                        }
                    )

                # 중요도 순으로 정렬하고 상위 5개만 유지 (중복 제거 후)
                normalized_items.sort(key=lambda x: x["importance"], reverse=True)
                normalized_items = normalized_items[:5]

                if normalized_items:
                    result[cat] = normalized_items
            return result

        return {
            "long_term_memory": norm_bucket(
                data.get("long_term_memory") or data.get("ltm")
            ),
        }
