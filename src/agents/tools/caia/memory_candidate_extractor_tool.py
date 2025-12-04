"""
Memory Candidate Extractor Tool
메모리 후보를 LLM 기반으로 추출하고 메모리 테이블에 저장하는 도구
"""

from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List

from src.agents.components.caia.memory_candidate_extractor import (
    MemoryCandidateExtractor,
)
from src.agents.components.caia.memory_compressor import MemoryCompressor
from src.agents.components.caia.memory_merger import MemoryMerger
from src.agents.tools.base_tool import BaseTool
from src.apps.api.user.user_manager import user_manager
from src.utils.log_collector import collector

logger = getLogger("agents.tools.memory_candidate_extractor")

# 상수 정의
DEFAULT_MEMORY_LEN_LIMIT = 3000
DEFAULT_IMPORTANCE = 0.7
DEFAULT_AGENT_ID = 1
MEMORY_TYPES = ("long_term_memory",)


class MemoryCandidateExtractorTool(BaseTool):
    """메모리 추출 도구 - 컴포넌트를 조합한 복합 도구"""

    name = "extract_and_save_memory_candidates"
    description = (
        "세션 요약으로부터 long_term_memory 메모리 후보를 추출하고 저장합니다."
    )

    def __init__(self, memory_len_limit: int = DEFAULT_MEMORY_LEN_LIMIT):
        self.memory_len_limit = memory_len_limit

    def _is_memory_long(self, memory: str) -> bool:
        """메모리 길이가 제한을 초과하는지 확인"""
        return len(memory) > self.memory_len_limit

    async def run_new(
        self,
        user_id: int,
        agent_id: int,
        user_query: str,
        chat_history: List,
        existing_memory: str,
    ) -> Dict[str, Any]:
        """새로운 메모리 추출 및 저장 프로세스"""
        logger.info(
            f"[MEMORY_EXTRACT] MemoryCandidateExtractorTool.run_new 시작 - user_id: {user_id}, user_query: {user_query[:100]}..."
        )

        try:
            # 1. 정보 추출
            logger.info(f"[MEMORY_EXTRACT] 새로운 정보 추출 시작")
            new_information = await self._extract_new_information(
                user_query, chat_history
            )
            logger.info(
                f"[MEMORY_EXTRACT] 새로운 정보 추출 완료: {new_information[:200]}..."
            )

            if new_information == "NONE":
                logger.info(f"[MEMORY_EXTRACT] 새로운 정보가 없어서 종료")
                return {"ok": True}

            # 2. 메모리 병합
            logger.info(f"[MEMORY_EXTRACT] 메모리 병합 시작")
            new_memory = await self._merge_memory(
                user_query=user_query,
                existing_memory=existing_memory,
                new_information=new_information,
            )
            logger.info(f"[MEMORY_EXTRACT] 메모리 병합 완료: {new_memory[:200]}...")

            # 3. 메모리 압축 (필요시)
            logger.info(f"[MEMORY_EXTRACT] 메모리 압축 확인")
            new_memory = await self._compress_memory_if_needed(new_memory)
            logger.info(f"[MEMORY_EXTRACT] 메모리 압축 완료: {new_memory[:200]}...")

            # 4. 메모리 업데이트
            logger.info(f"[MEMORY_EXTRACT] 메모리 업데이트 시작")
            self._update_memory(user_id, agent_id, new_memory)
            logger.info(f"[MEMORY_EXTRACT] 메모리 업데이트 완료")

            logger.info(f"[MEMORY_EXTRACT] MemoryCandidateExtractorTool.run_new 완료")
            return {"ok": True}

        except Exception as e:
            logger.error(
                f"[MEMORY_EXTRACT] MemoryCandidateExtractorTool.run_new failed: {e}"
            )
            return {"ok": False, "error": str(e)}

    async def _extract_new_information(
        self, user_query: str, chat_history: List
    ) -> str:
        """새로운 정보 추출"""
        extractor = MemoryCandidateExtractor()
        new_information = await extractor.extract_new(
            user_query=user_query,
            chat_history=chat_history,
            time=datetime.now().strftime("[%Y.%m.%d %H:%M:%S]"),
        )
        collector.log("new_information", new_information)
        return new_information

    async def _merge_memory(
        self, user_query: str, existing_memory: str, new_information: str
    ) -> str:
        """메모리 병합"""
        merger = MemoryMerger()
        new_memory = await merger.merge(
            user_query=user_query,
            existing_memory=existing_memory,
            new_information=new_information,
        )
        collector.log("existing_memory", existing_memory)
        collector.log("new_memory", new_memory)
        return new_memory

    async def _compress_memory_if_needed(self, memory: str) -> str:
        """메모리 압축 (필요시)"""
        if not self._is_memory_long(memory):
            return memory

        compressor = MemoryCompressor()
        compressed_memory = await compressor.compress(memory=memory)
        collector.log("compressed_memory", compressed_memory)
        return compressed_memory

    def _update_memory(self, user_id: int, agent_id: int, new_memory: str) -> None:
        """메모리 업데이트"""
        user_manager.update_memory_async(
            user_id=user_id,
            content=new_memory,
            memory_type="long_term_memory",
            importance=1.0,
            agent_id=agent_id,
            category="LTM",
            source="fact",
        )

    async def run(self, tool_input: Any) -> Dict[str, Any]:
        """메모리 추출 및 저장 실행"""
        logger.info(
            f"[MEMORY_EXTRACT] MemoryCandidateExtractorTool.run 시작 - tool_input: {tool_input}"
        )

        if not isinstance(tool_input, dict):
            logger.error(
                f"[MEMORY_EXTRACT] tool_input이 딕셔너리가 아님: {type(tool_input)}"
            )
            return {"error": "tool_input must be a dictionary", "success": False}

        try:
            params = self._extract_tool_params(tool_input)
            logger.info(f"[MEMORY_EXTRACT] 파라미터 추출 완료: {params}")

            # 메모리 추출
            extracted = await self._extract_memories(params)

            # 메모리 저장
            saved_records = await self._save_extracted_memories(extracted, params)

            # 결과 요약
            self._log_extraction_summary(extracted, saved_records)

            logger.info(
                f"[MEMORY_EXTRACT] MemoryCandidateExtractorTool.run 완료 - saved: {len(saved_records)}개"
            )
            return {"ok": True, "saved": saved_records, "success": True}

        except Exception as e:
            logger.error(f"[MEMORY_EXTRACT] MemoryCandidateExtractorTool failed: {e}")
            return {"ok": False, "error": str(e), "success": False}

    def _extract_tool_params(self, tool_input: Dict[str, Any]) -> Dict[str, Any]:
        """도구 입력 파라미터 추출"""
        return {
            "user_id": int(tool_input.get("user_id")),
            "agent_id": (
                int(tool_input.get("agent_id"))
                if tool_input.get("agent_id") is not None
                else DEFAULT_AGENT_ID
            ),
            "session_content": str(tool_input.get("session_content", "")),
            "user_query": str(tool_input.get("user_query", "")),
            "default_importance": float(
                tool_input.get("importance", DEFAULT_IMPORTANCE)
            ),
        }

    async def _extract_memories(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """메모리 추출"""
        logger.info(
            f"[MEMORY_EXTRACT] 메모리 추출 시작 - 사용자: {params['user_id']}, 질의: {params['user_query'][:100]}..."
        )
        extractor = MemoryCandidateExtractor()
        extracted = await extractor.extract(
            session_content=params["session_content"],
            user_query=params["user_query"],
        )
        logger.info(f"[MEMORY_EXTRACT] 메모리 추출 완료 - 결과: {extracted}")
        return extracted

    async def _save_extracted_memories(
        self, extracted: Dict[str, Any], params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """추출된 메모리 저장"""
        saved_records = []
        logger.info(f"[MEMORY_EXTRACT] 메모리 저장 시작 - 추출된 데이터: {extracted}")

        for mem_type in MEMORY_TYPES:
            bucket = extracted.get(mem_type) or {}
            logger.info(
                f"[MEMORY_EXTRACT] 처리 중인 메모리 타입: {mem_type}, 버킷: {bucket}"
            )

            for category, items in bucket.items():
                logger.info(
                    f"[MEMORY_EXTRACT] 처리 중인 카테고리: {category}, 아이템 수: {len(items)}"
                )

                for item in items:
                    if not self._is_valid_memory_item(item):
                        logger.warning(
                            f"[MEMORY_EXTRACT] 유효하지 않은 메모리 아이템 건너뜀: {item}"
                        )
                        continue

                    memory_record = self._create_memory_record(
                        item, mem_type, category, params
                    )
                    logger.info(f"[MEMORY_EXTRACT] 메모리 레코드 생성: {memory_record}")

                    self._save_memory_async(memory_record, params)
                    saved_records.append(memory_record)
                    logger.info(
                        f"[MEMORY_EXTRACT] 메모리 저장 완료: {memory_record['content'][:50]}..."
                    )

        logger.info(f"[MEMORY_EXTRACT] 총 {len(saved_records)}개 메모리 저장 완료")
        return saved_records

    def _is_valid_memory_item(self, item: Dict[str, Any]) -> bool:
        """메모리 아이템 유효성 검사"""
        content = str(item.get("content", "")).strip()
        return bool(content)

    def _create_memory_record(
        self, item: Dict[str, Any], mem_type: str, category: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """메모리 레코드 생성"""
        content = str(item.get("content", "")).strip()
        importance = float(item.get("importance", params["default_importance"]))
        source = (
            "fact"
            if str(item.get("source", "inferred")).lower() == "fact"
            else "inferred"
        )
        mapped_type = "semantic" if mem_type == "long_term_memory" else mem_type

        return {
            "memory_type": mapped_type,
            "category": category,
            "source": source,
            "importance": importance,
            "content": content,
        }

    def _save_memory_async(
        self, memory_record: Dict[str, Any], params: Dict[str, Any]
    ) -> None:
        """메모리 비동기 저장"""

        user_manager.save_memory_async(
            user_id=params["user_id"],
            content=memory_record["content"],
            memory_type=memory_record["memory_type"],
            importance=memory_record["importance"],
            agent_id=params["agent_id"],
            category=memory_record["category"],
            source=memory_record["source"],
        )

    def _log_extraction_summary(
        self, extracted: Dict[str, Any], saved_records: List[Dict[str, Any]]
    ) -> None:
        """추출 결과 요약 로깅"""
        total_extracted = sum(
            len(items)
            for mem_type in MEMORY_TYPES
            for items in (extracted.get(mem_type) or {}).values()
        )
        total_saved = len(saved_records)

        logger.info(
            f"[MEMORY_EXTRACT] 추출된 메모리: {total_extracted}개, 저장된 메모리: {total_saved}개"
        )

        if saved_records:
            category_summary = self._build_category_summary(saved_records)
            summary_parts = [
                f"{cat}({info['count']})" for cat, info in category_summary.items()
            ]
            logger.info(
                f"[MEMORY_EXTRACT] 저장된 메모리 카테고리: {', '.join(summary_parts)}"
            )
        else:
            logger.warning("[MEMORY_EXTRACT] 저장된 메모리가 없습니다")

    def _build_category_summary(
        self, saved_records: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """카테고리별 요약 생성"""
        category_summary = {}
        for record in saved_records:
            category = record["category"]
            if category not in category_summary:
                category_summary[category] = {
                    "count": 0,
                    "type": record["memory_type"],
                }
            category_summary[category]["count"] += 1
        return category_summary
