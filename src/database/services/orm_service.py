"""
메모리 관련 데이터베이스 서비스

Memory 관련 서비스들
"""

from logging import getLogger
from typing import List, Optional

from sqlalchemy import desc, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Memory, MemoryType, MemorySource
from .base_orm_service import ORMService

logger = getLogger("database")


class MemoryService(ORMService[Memory]):
    """메모리 서비스"""

    def __init__(self):
        super().__init__(Memory)

    def get_user_memories(
        self,
        db: Session,
        user_id: int,
        agent_id: int,
        memory_type: Optional[MemoryType] = None,
        category: Optional[str] = None,
    ) -> List[Memory]:
        """사용자의 메모리 조회"""
        try:
            query = db.query(Memory).filter(
                Memory.user_id == user_id, Memory.agent_id == agent_id
            )

            if memory_type:
                query = query.filter(Memory.memory_type == memory_type)

            if category:
                query = query.filter(Memory.category == category)

            return query.order_by(
                desc(Memory.importance), desc(Memory.accessed_at)
            ).all()
        except SQLAlchemyError as e:
            logger.error(f"사용자 메모리 조회 실패: {e}")
            return []

    def get_by_category(
        self, db: Session, user_id: int, agent_id: int, memory_type: MemoryType, category: str
    ) -> Optional[Memory]:
        """카테고리별 메모리 조회"""
        try:
            return (
                db.query(Memory)
                .filter(
                    Memory.user_id == user_id,
                    Memory.agent_id == agent_id,
                    Memory.memory_type == memory_type,
                    Memory.category == category,
                )
                .order_by(desc(Memory.created_at))
                .first()
            )
        except SQLAlchemyError as e:
            logger.error(f"카테고리별 메모리 조회 실패: {e}")
            return None

    def create_or_update_memory(
        self,
        db: Session,
        user_id: int,
        agent_id: int,
        content: str,
        memory_type: str,
        importance: float,
        category: str,
        source: str,
    ) -> Optional[Memory]:
        """메모리 생성 또는 업데이트"""
        try:
            # memory_type을 MemoryType enum으로 변환
            if isinstance(memory_type, str):
                # 문자열 값을 MemoryType enum으로 변환
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
                memory_type = memory_type_mapping.get(memory_type_lower)
                if memory_type is None:
                    # 매핑되지 않은 경우 원래 값으로 시도 (이미 enum인 경우)
                    try:
                        memory_type = MemoryType(memory_type)
                    except ValueError:
                        logger.error(f"알 수 없는 memory_type: {memory_type}")
                        return None
            elif not isinstance(memory_type, MemoryType):
                logger.error(f"잘못된 memory_type 타입: {type(memory_type)}")
                return None

            # source를 MemorySource enum으로 변환
            if isinstance(source, str):
                source_lower = source.lower()
                if source_lower == "fact":
                    source_enum = MemorySource.FACT
                else:
                    source_enum = MemorySource.INFERRED
            elif isinstance(source, MemorySource):
                source_enum = source
            else:
                logger.warning(f"잘못된 source 타입: {type(source)}, 기본값 'inferred' 사용")
                source_enum = MemorySource.INFERRED

            # 기존 메모리 조회
            existing = self.get_by_category(
                db, user_id, agent_id, memory_type, category
            )

            if existing:
                # 기존 메모리 업데이트 - LTM의 경우 내용을 추가
                if memory_type == MemoryType.LTM:
                    # LTM 메모리는 기존 내용에 새 내용을 추가
                    existing.content = f"{existing.content}\n\n{content}"
                else:
                    # 다른 메모리 타입은 기존 내용을 덮어씀
                    existing.content = content
                existing.importance = max(existing.importance, importance)
                existing.source = source_enum
                db.commit()
                db.refresh(existing)
                return existing
            else:
                # 새 메모리 생성
                return self.create(
                    db,
                    user_id=user_id,
                    agent_id=agent_id,
                    content=content,
                    memory_type=memory_type,
                    importance=importance,
                    category=category,
                    source=source_enum,
                )
        except SQLAlchemyError as e:
            logger.error(f"메모리 생성/업데이트 실패: {e}")
            return None

    def search_memories(
        self, db: Session, user_id: int, agent_id: int, query_text: str
    ) -> List[Memory]:
        """메모리 내용 검색"""
        try:
            return (
                db.query(Memory)
                .filter(
                    Memory.user_id == user_id,
                    Memory.agent_id == agent_id,
                    Memory.content.contains(query_text),
                )
                .order_by(desc(Memory.importance), desc(Memory.accessed_at))
                .all()
            )
        except SQLAlchemyError as e:
            logger.error(f"메모리 검색 실패: {e}")
            return []

    def update_accessed_at(self, db: Session, memory_id: int) -> bool:
        """메모리 접근 시간 업데이트"""
        try:
            memory = db.query(Memory).filter(Memory.id == memory_id).first()
            if memory:
                memory.accessed_at = func.current_timestamp()
                db.commit()
                return True
            return False
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"메모리 접근 시간 업데이트 실패: {e}")
            return False


# 서비스 인스턴스
memory_service = MemoryService()
