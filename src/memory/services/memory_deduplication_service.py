"""
Memory Deduplication Service

메모리 중복 체크 및 유사도 검사를 담당하는 서비스
LLM을 활용한 지능적인 중복 감지
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.database.connection import get_db
from src.database.models import Memory, MemoryType, MemorySource
from src.database.services import memory_service
from src.llm.manager import LLMManager

logger = logging.getLogger("memory.deduplication")


class MemoryDeduplicationService:
    """메모리 중복 체크 및 유사도 검사 서비스"""

    def __init__(self):
        self.llm_manager = LLMManager()

    async def check_duplicate(
        self,
        user_id: int,
        agent_id: int,
        content: str,
        memory_type: str,
        category: Optional[str] = None,
        threshold: float = 0.9,
    ) -> Tuple[bool, Optional[Memory]]:
        """
        메모리 중복 체크 (LLM 기반)

        Args:
            user_id: 사용자 ID
            agent_id: 에이전트 ID
            content: 새 메모리 내용
            memory_type: 메모리 타입
            category: 카테고리 (선택사항)
            threshold: 중복 판정 임계값 (0.0 ~ 1.0)

        Returns:
            (중복 여부, 기존 메모리 객체)
        """
        try:
            db = next(get_db())

            # 동일 카테고리의 기존 메모리들 조회
            existing_memories = self._get_candidate_memories(
                db, user_id, agent_id, memory_type, category
            )

            if not existing_memories:
                return False, None

            # 중복 체크 비활성화 - 항상 새 메모리로 처리
            return False, None

        except Exception as e:
            logger.error(f"중복 체크 실패: {e}")
            return False, None
        finally:
            if "db" in locals():
                db.close()

    def _get_candidate_memories(
        self,
        db,
        user_id: int,
        agent_id: int,
        memory_type: str,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Memory]:
        """중복 체크 대상 메모리들 조회"""
        try:
            # memory_type 문자열을 MemoryType enum으로 변환
            if isinstance(memory_type, str):
                memory_type_lower = memory_type.lower()
                memory_type_mapping = {
                    "ltm": MemoryType.LTM,
                    "long_term_memory": MemoryType.LTM,
                    "stm": MemoryType.STM,
                    "short_term_memory": MemoryType.STM,
                    "episodic": MemoryType.EPISODIC,
                    "semantic": MemoryType.SEMANTIC,
                    "procedural": MemoryType.PROCEDURAL,
                }
                memory_type_enum = memory_type_mapping.get(memory_type_lower)
                if memory_type_enum is None:
                    try:
                        memory_type_enum = MemoryType(memory_type_lower)
                    except ValueError:
                        logger.error(f"알 수 없는 memory_type: {memory_type}")
                        return []
            elif isinstance(memory_type, MemoryType):
                memory_type_enum = memory_type
            else:
                logger.error(f"잘못된 memory_type 타입: {type(memory_type)}")
                return []
            
            query = db.query(Memory).filter(
                Memory.user_id == user_id,
                Memory.agent_id == agent_id,
                Memory.memory_type == memory_type_enum,
            )

            if category:
                query = query.filter(Memory.category == category)

            return query.order_by(Memory.created_at.desc()).limit(limit).all()

        except Exception as e:
            logger.error(f"후보 메모리 조회 실패: {e}")
            return []

    def _calculate_keyword_similarity(self, content1: str, content2: str) -> float:
        """키워드 기반 유사도 계산 (fallback)"""
        try:
            words1 = set(content1.lower().split())
            words2 = set(content2.lower().split())

            if not words1 or not words2:
                return 0.0

            intersection = len(words1.intersection(words2))
            union = len(words1.union(words2))

            return intersection / union if union > 0 else 0.0

        except Exception as e:
            logger.error(f"키워드 유사도 계산 실패: {e}")
            return 0.0

    def should_merge_memories(
        self,
        existing_memory: Memory,
        new_content: str,
        category: str,
        source: str,
    ) -> bool:
        """
        메모리 통합 여부 결정

        Args:
            existing_memory: 기존 메모리
            new_content: 새 내용
            category: 카테고리
            source: 소스 (문자열 또는 MemorySource enum)

        Returns:
            통합 여부
        """
        # source를 문자열로 변환 (enum인 경우 value 사용)
        if isinstance(source, MemorySource):
            source_str = source.value
        else:
            source_str = str(source).lower()

        # 인사정보는 항상 새로 저장
        if category == "인사정보":
            return False

        # fact 업데이트는 기존 메모리 업데이트
        overwrite_categories = {
            "이름",
            "직업",
            "기술",
            "언어",
            "프레임워크",
            "도구",
            "플랫폼",
            "경력정보",
            "주업무",
            "프로젝트",
        }

        if source_str == "fact" and category in overwrite_categories:
            return True

        # 일반적인 정보는 통합
        return True

    def merge_memory_content(
        self,
        existing_content: str,
        new_content: str,
        category: str,
    ) -> str:
        """
        메모리 내용 통합

        Args:
            existing_content: 기존 내용
            new_content: 새 내용
            category: 카테고리

        Returns:
            통합된 내용
        """
        if category == "인사정보":
            # 인사정보는 새로 저장하므로 기존 내용 반환
            return existing_content

        # 일반적인 정보는 내용 추가
        return f"{existing_content}\n{new_content}"
