"""
MySQL Memory Provider

MySQL을 사용한 메모리 저장 및 검색 구현
"""

from __future__ import annotations

import json
import logging
import os
from logging import getLogger
from typing import Any, Dict, List, Optional

import mysql.connector
from mysql.connector import pooling
from mysql.connector.errors import Error as MySQLError

from src.database.connection import get_db
from src.database.models import Agent, Memory, MemoryType, MemorySource
from src.database.services import memory_service
from src.memory.services import MemoryDeduplicationService

logger = getLogger("memory.mysql")

# 상수 정의
DEFAULT_POOL_SIZE = 32
DEFAULT_TIMEZONE = "Asia/Seoul"
MEMORY_TYPE_MAPPING = {
    "LTM": MemoryType.LTM,
    "ltm": MemoryType.LTM,
    "long_term_memory": MemoryType.LTM,
    "STM": MemoryType.STM,
    "stm": MemoryType.STM,
    "short_term_memory": MemoryType.STM,
    "episodic": MemoryType.EPISODIC,
    "semantic": MemoryType.SEMANTIC,
    "procedural": MemoryType.PROCEDURAL,
}


class MySQLMemoryProvider:
    """MySQL 기반 메모리 프로바이더 (단순 CRUD)"""

    def __init__(self, connection_config: Dict[str, Any]):
        """초기화

        Args:
            connection_config: MySQL 연결 설정
        """
        self.connection_config = connection_config
        self.pool = None
        self._init_connection_pool()

        # 서비스 초기화
        self.deduplication_service = MemoryDeduplicationService()

    def _init_connection_pool(self):
        """연결 풀 초기화"""
        try:
            config = self._build_pool_config()
            self.pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="memory_pool", **config
            )
        except MySQLError as e:
            logger.error(f"MySQL 연결 풀 초기화 실패: {e}")
            raise

    def _build_pool_config(self) -> Dict[str, Any]:
        """연결 풀 설정 구성"""
        pool_size = int(os.getenv("MYSQL_POOL_SIZE", str(DEFAULT_POOL_SIZE)))
        pool_reset_session = (
            os.getenv("MYSQL_POOL_RESET_SESSION", "true").lower() == "true"
        )
        autocommit = os.getenv("MYSQL_AUTOCOMMIT", "true").lower() == "true"
        raise_on_warnings = (
            os.getenv("MYSQL_RAISE_ON_WARNINGS", "true").lower() == "true"
        )
        timezone = self.connection_config.get("timezone", DEFAULT_TIMEZONE)

        config = self.connection_config.copy()
        config.update(
            {
                "pool_size": pool_size,
                "pool_reset_session": pool_reset_session,
                "autocommit": autocommit,
                "raise_on_warnings": raise_on_warnings,
                "time_zone": timezone,
            }
        )
        return config

    def _set_connection_timezone(self, connection):
        """연결된 MySQL 세션에 타임존 설정"""
        try:
            timezone = self.connection_config.get("timezone", DEFAULT_TIMEZONE)
            cursor = connection.cursor()
            cursor.execute(f"SET time_zone = '{timezone}'")
            cursor.close()
        except MySQLError as e:
            logger.warning(f"MySQL 타임존 설정 실패: {e}")

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """간단한 텍스트 유사도 계산 (0.0 ~ 1.0)"""
        if not text1 or not text2:
            return 0.0

        # 단어 단위로 분할
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 or not words2:
            return 0.0

        # Jaccard 유사도 계산
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

    async def save_memory(
        self, user_id: int, content: str, metadata: Dict[str, Any] = None
    ) -> bool:
        """메모리 저장 (단순화된 버전)"""
        metadata = metadata or {}
        memory_params = self._extract_memory_params(metadata)

        # LTM 메모리는 기존 내용에 추가하도록 처리
        if memory_params["memory_type"] == MemoryType.LTM:
            return await self._save_ltm_memory(user_id, content, memory_params)

        return await self._save_regular_memory(user_id, content, memory_params)

    def _extract_memory_params(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """메타데이터에서 메모리 파라미터 추출"""
        memory_type = metadata.get("memory_type", "long_term_memory")
        # 문자열인 경우 MemoryType enum으로 변환
        if isinstance(memory_type, str):
            memory_type_lower = memory_type.lower()
            memory_type = MEMORY_TYPE_MAPPING.get(memory_type_lower)
            if memory_type is None:
                # 매핑되지 않은 경우 직접 변환 시도
                try:
                    memory_type = MemoryType(memory_type_lower)
                except ValueError:
                    # 기본값 사용
                    logger.warning(f"알 수 없는 memory_type: {memory_type}, 기본값 'LTM' 사용")
                    memory_type = MemoryType.LTM
        elif not isinstance(memory_type, MemoryType):
            # 이미 MemoryType enum인 경우 그대로 사용
            logger.warning(f"잘못된 memory_type 타입: {type(memory_type)}, 기본값 'LTM' 사용")
            memory_type = MemoryType.LTM

        # source를 MemorySource enum으로 변환
        source_str = (metadata.get("source") or "inferred").lower()
        if source_str == "fact":
            source_enum = MemorySource.FACT
        else:
            source_enum = MemorySource.INFERRED

        return {
            "memory_type": memory_type,
            "importance": metadata.get("importance", 1.0),
            "agent_id": metadata.get("agent_id"),
            "category": metadata.get("category"),
            "source": source_enum,
        }

    async def _save_ltm_memory(
        self, user_id: int, content: str, memory_params: Dict[str, Any]
    ) -> bool:
        """LTM 메모리 저장"""
        try:
            # context manager를 사용하여 세션 자동 정리
            from src.utils.db_utils import get_db_session
            
            with get_db_session() as db:
                memory = memory_service.create_or_update_memory(
                    db,
                    user_id,
                    memory_params["agent_id"],
                    content,
                    memory_params["memory_type"],
                    memory_params["importance"],
                    memory_params["category"],
                    memory_params["source"],
                )

                if memory:
                    return True
                else:
                    logger.error(
                        f"LTM 메모리 저장 실패: user_id={user_id}, agent_id={memory_params['agent_id']}"
                    )
                    return False
        except Exception as e:
            logger.error(f"LTM 메모리 저장 실패 (User ID: {user_id}): {e}")
            return False

    async def _save_regular_memory(
        self, user_id: int, content: str, memory_params: Dict[str, Any]
    ) -> bool:
        """일반 메모리 저장 (중복 체크 포함)"""
        db = None
        try:
            # 1. 중복 체크
            # memory_type을 문자열로 변환 (enum인 경우 value 사용)
            memory_type_str = (
                memory_params["memory_type"].value
                if isinstance(memory_params["memory_type"], MemoryType)
                else str(memory_params["memory_type"])
            )
            is_duplicate, existing_memory = (
                await self.deduplication_service.check_duplicate(
                    user_id,
                    memory_params["agent_id"],
                    content,
                    memory_type_str,
                    memory_params["category"],
                )
            )

            if is_duplicate and existing_memory:
                return await self._handle_duplicate_memory(
                    existing_memory, content, memory_params
                )

            # 2. 새 메모리 생성 (context manager 사용)
            from src.utils.db_utils import get_db_session
            
            with get_db_session() as db:
                memory = memory_service.create_or_update_memory(
                    db,
                    user_id,
                    memory_params["agent_id"],
                    content,
                    memory_params["memory_type"],
                    memory_params["importance"],
                    memory_params["category"],
                    memory_params["source"],
                )

                if memory:
                    return True
                else:
                    logger.error(
                        f"메모리 저장 실패: user_id={user_id}, agent_id={memory_params['agent_id']}"
                    )
                    return False

        except Exception as e:
            logger.error(f"메모리 저장 실패 (User ID: {user_id}): {e}")
            return False

    async def _handle_duplicate_memory(
        self, existing_memory, content: str, memory_params: Dict[str, Any]
    ) -> bool:
        """중복 메모리 처리"""
        should_merge = self.deduplication_service.should_merge_memories(
            existing_memory, content, memory_params["category"], memory_params["source"]
        )

        if should_merge:
            # 기존 메모리 업데이트
            merged_content = self.deduplication_service.merge_memory_content(
                existing_memory.content, content, memory_params["category"]
            )
            existing_memory.content = merged_content
            existing_memory.importance = max(
                existing_memory.importance, memory_params["importance"]
            )
            existing_memory.source = memory_params["source"]

            db = next(get_db())
            db.commit()
            return True
        else:
            # 중복이지만 새로 저장 (인사정보 등)
            return False

    def search_memories(
        self,
        user_id: int,
        agent_id: int,
        limit: int = 10,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """간단한 최신순 조회 (ORM 사용)"""
        db = None
        try:
            db = next(get_db())
            memories = memory_service.get_user_memories(db, user_id, agent_id)
            memories = sorted(
                memories, key=lambda m: (m.created_at, m.importance), reverse=True
            )[:limit]
            return [self._format_memory_result(memory) for memory in memories]
        except Exception as e:
            logger.error(f"메모리 검색 실패: {e}")
            return []
        finally:
            if db:
                db.close()

    def _format_memory_result(self, memory) -> Dict[str, Any]:
        """메모리 객체를 딕셔너리로 포맷팅"""
        return {
            "id": memory.id,
            "content": memory.content,
            "memory_type": memory.memory_type,
            "importance": memory.importance,
            "category": memory.category,
            "source": memory.source,
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "accessed_at": (
                memory.accessed_at.isoformat() if memory.accessed_at else None
            ),
        }

    def update_memory_access(self, memory_id: int) -> bool:
        """메모리 접근 시간 업데이트 (ORM 사용)"""
        db = None
        try:
            db = next(get_db())
            memory = memory_service.get_by_id(db, memory_id)

            if not memory:
                logger.error(f"메모리를 찾을 수 없습니다: ID {memory_id}")
                return False

            from datetime import datetime

            memory.accessed_at = datetime.now()
            db.commit()
            return True

        except Exception as e:
            logger.error(f"메모리 접근 시간 업데이트 실패: {e}")
            return False
        finally:
            if db:
                db.close()

    def delete_memory(self, memory_id: int, user_id: int) -> bool:
        """메모리 삭제 (ORM 사용)"""
        db = None
        try:
            db = next(get_db())
            memory = memory_service.get_by_id(db, memory_id)

            if not memory:
                logger.warning(f"메모리를 찾을 수 없습니다: ID {memory_id}")
                return False

            if memory.user_id != user_id:
                logger.warning(
                    f"메모리 삭제 권한 없음. memory_id: {memory_id}, user_id: {user_id}"
                )
                return False

            memory_service.delete(db, memory_id)
            return True

        except Exception as e:
            logger.error(f"메모리 삭제 실패: {e}")
            return False
        finally:
            if db:
                db.close()

    def delete_memories_by_category(
        self, user_id: int, agent_id: int, category: str, memory_type: str
    ) -> bool:
        """카테고리별 메모리 삭제 (ORM 사용)"""
        db = None
        try:
            db = next(get_db())
            memories = memory_service.get_user_memories(
                db, user_id, agent_id, memory_type, category
            )

            if not memories:
                return True

            deleted_count = sum(
                1 for memory in memories if memory_service.delete(db, memory.id)
            )
            return True

        except Exception as e:
            logger.error(f"카테고리별 메모리 삭제 실패: {e}")
            return False
        finally:
            if db:
                db.close()

    def cleanup_old_memories(self, days: int = 30) -> int:
        """오래된 메모리 정리 (ORM 사용)"""
        db = None
        try:
            db = next(get_db())
            from datetime import datetime, timedelta

            cutoff_date = datetime.now() - timedelta(days=days)
            old_memories = (
                db.query(Memory)
                .filter(Memory.created_at < cutoff_date, Memory.importance < 0.5)
                .all()
            )

            deleted_count = len(old_memories)
            for memory in old_memories:
                db.delete(memory)

            db.commit()
            return deleted_count

        except Exception as e:
            logger.error(f"메모리 정리 실패: {e}")
            return 0
        finally:
            if db:
                db.close()

    def get_memory_stats(self, user_id: int) -> Dict[str, Any]:
        """메모리 통계 조회 (ORM 사용)"""
        db = None
        try:
            db = next(get_db())
            memories = db.query(Memory).filter(Memory.user_id == user_id).all()

            if not memories:
                return {}

            total_memories = len(memories)
            avg_importance = sum(m.importance for m in memories) / total_memories
            latest_memory = max(memories, key=lambda m: m.created_at).created_at

            return {
                "total_memories": total_memories,
                "avg_importance": float(avg_importance),
                "latest_memory": latest_memory.isoformat() if latest_memory else None,
            }

        except Exception as e:
            logger.error(f"메모리 통계 조회 실패: {e}")
            return {}
        finally:
            if db:
                db.close()

    def get_recent_memories(
        self, user_id: int, agent_id: int, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """최근 메모리 조회 (에이전트 스코프) - ORM 사용"""
        db = None
        try:
            db = next(get_db())
            memories = memory_service.get_user_memories(db, user_id, agent_id)
            memories = sorted(memories, key=lambda m: m.created_at, reverse=True)[
                :limit
            ]
            return [self._format_memory_result(memory) for memory in memories]
        except Exception as e:
            logger.error(f"최근 메모리 조회 실패: {e}")
            return []
        finally:
            if db:
                db.close()

    def get_agent_id_by_code(self, agent_code: str) -> Optional[int]:
        """에이전트 코드로 agent_id 조회 (ORM 사용)"""
        db = None
        try:
            db = next(get_db())
            agent = db.query(Agent).filter(Agent.code == agent_code).first()
            return agent.id if agent else None
        except Exception as e:
            logger.error(f"에이전트 조회 실패 (code={agent_code}): {e}")
            return None
        finally:
            if db:
                db.close()

    def get_agent_info_by_code(self, agent_code: str) -> Optional[Dict[str, Any]]:
        """에이전트 코드로 에이전트 정보 조회 (id, name, code) - ORM 사용"""
        db = None
        try:
            db = next(get_db())
            agent = db.query(Agent).filter(Agent.code == agent_code).first()

            if not agent:
                return None

            return {
                "id": agent.id,
                "code": agent.code,
                "name": agent.name,
                "executive_only": agent_code == "caia",  # CAIA 에이전트는 임원 전용
            }
        except Exception as e:
            logger.error(f"에이전트 정보 조회 실패 (code={agent_code}): {e}")
            return None
        finally:
            if db:
                db.close()

    def close(self):
        """연결 풀 종료"""
        if self.pool:
            try:
                # MySQLConnectionPool에는 close 메서드가 없습니다.
                # 연결 풀의 모든 연결을 닫기 위해 풀을 None으로 설정합니다.
                # Python의 가비지 컬렉션이 연결을 정리합니다.
                self.pool = None
                logger.debug("MySQL 연결 풀이 종료되었습니다.")
            except Exception as e:
                logger.error(f"MySQL 연결 풀 종료 중 오류: {e}")
                self.pool = None

    def _column_exists(self, cursor, table: str, column: str) -> bool:
        """컬럼 존재 여부 확인"""
        try:
            cursor.execute(f"SHOW COLUMNS FROM {table} LIKE %s", (column,))
            return bool(cursor.fetchone())
        except Exception:
            return False
