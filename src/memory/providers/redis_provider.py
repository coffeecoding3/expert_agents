"""
Redis Memory Provider

간단한 Redis 기반 메모리 저장/검색 구현
"""

from __future__ import annotations

import json
import math
import time
import uuid
from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List, Optional

import redis

logger = getLogger("memory.redis")


class RedisMemoryProvider:
    """Redis 기반 메모리 프로바이더

    키 스키마:
    - mem:{agent_id}:{user_id} -> List[JSON]
    - mem:id -> 글로벌 increment id
    """

    def __init__(self, config: Dict[str, Any]):
        """초기화

        Args:
            config: {"redis_url": str} 또는 {"host", "port", "password", "db"}
        """
        self.config = config
        self.client = self._create_client(config)

    def _create_client(self, config: Dict[str, Any]) -> redis.Redis:
        if "redis_url" in config and config["redis_url"]:
            return redis.from_url(config["redis_url"])  # type: ignore[arg-type]
        return redis.Redis(
            host=config.get("host", "localhost"),
            port=int(config.get("port", 6379)),
            password=config.get("password"),
            db=int(config.get("db", 0)),
            decode_responses=True,
        )

    def _key(
        self,
        user_id: int,
        agent_id: int,
        session_id: Optional[str] = None,
        timestamp: Optional[int] = None,
    ) -> str:
        # 날짜 기반 키 생성 (YYYY-MM-DD 형식)
        if timestamp:
            date_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")

        if session_id:
            return f"mem:{user_id}:{date_str}:{session_id}"
        else:
            # session_id가 없으면 unknown_{uuid} 형식으로 생성
            unknown_session_id = f"unknown_{str(uuid.uuid4())}"
            return f"mem:{user_id}:{date_str}:{unknown_session_id}"

    def save_memory(
        self,
        user_id: int,
        content: Dict[str, str],
        metadata: Dict[str, Any] | None = None,
    ) -> bool:
        try:
            metadata = metadata or {}

            # session_id가 없으면 unknown_{uuid} 형식으로 생성
            session_id = metadata.get("session_id")
            if not session_id:
                session_id = f"unknown_{str(uuid.uuid4())}"
                metadata["session_id"] = session_id

            # 현재 timestamp 생성
            current_timestamp = int(time.time())

            memory_id = self.client.incr("mem:id")
            item = {
                "id": int(memory_id),
                "user_id": user_id,
                "agent_id": metadata.get("agent_id"),
                "content": content,
                "memory_type": metadata.get("memory_type", "episodic"),
                "importance": metadata.get("importance", 1.0),
                "category": metadata.get("category"),
                "session_id": session_id,
                "created_timestamp": current_timestamp,
            }
            key = self._key(
                user_id, metadata.get("agent_id") or 0, session_id, current_timestamp
            )
            self.client.rpush(key, json.dumps(item))
            return True
        except Exception as e:
            logger.error(f"Redis save_memory failed: {e}")
            return False

    def search_memories(
        self,
        user_id: int,
        agent_id: int,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        try:
            # 새로운 키 형식에 맞게 패턴 검색
            pattern = f"mem:{user_id}:*"
            keys = self.client.keys(pattern)

            if not keys:
                return []

            # 모든 키에서 메모리 수집
            all_memories = []
            for key in keys:
                values = self.client.lrange(key, 0, -1)
                for v in values:
                    try:
                        item = json.loads(v)
                        all_memories.append(item)
                    except Exception:
                        continue

            # timestamp 기준으로 정렬 (최신순)
            all_memories.sort(key=lambda x: x.get("created_timestamp", 0), reverse=True)

            return all_memories[:limit]
        except Exception as e:
            logger.error(f"Redis search_memories failed: {e}")
            return []

    def update_memory_access(self, memory_id: int) -> bool:
        # 간단 구현: 액세스 시간 미관리
        return True

    def delete_memory(self, memory_id: int, user_id: int) -> bool:
        # 간단 구현: 전체 스캔 후 해당 id 제거
        try:
            # 새로운 키 형식에 맞게 패턴 검색
            pattern = f"mem:{user_id}:*"
            keys = self.client.keys(pattern)

            for key in keys:
                values = self.client.lrange(key, 0, -1)
                for v in values:
                    try:
                        item = json.loads(v)
                        if item.get("id") == memory_id:
                            self.client.lrem(key, 1, v)
                            return True
                    except Exception:
                        continue
            return False
        except Exception as e:
            logger.error(f"Redis delete_memory failed: {e}")
            return False

    def delete_memories_by_category(
        self, user_id: int, agent_id: int, category: str, memory_type: str
    ) -> bool:
        """카테고리별 메모리 삭제 (Redis)

        Args:
            user_id: 사용자 ID
            agent_id: 에이전트 ID
            category: 카테고리
            memory_type: 메모리 타입

        Returns:
            삭제 성공 여부
        """
        try:
            # 새로운 키 형식에 맞게 패턴 검색
            pattern = f"mem:{user_id}:*"
            keys = self.client.keys(pattern)

            if not keys:
                return True

            # 카테고리와 메모리 타입이 일치하는 항목들 삭제
            deleted_count = 0
            for key in keys:
                values = self.client.lrange(key, 0, -1)
                for v in values:
                    try:
                        item = json.loads(v)
                        if (
                            item.get("category") == category
                            and item.get("memory_type") == memory_type
                        ):
                            self.client.lrem(key, 1, v)
                            deleted_count += 1
                    except Exception:
                        continue

            return True

        except Exception as e:
            logger.error(f"Redis delete_memories_by_category failed: {e}")
            return False

    def cleanup_old_memories(self, days: int = 30) -> int:
        # 간단 구현: 미지원
        return 0

    def get_memory_stats(self, user_id: int) -> Dict[str, Any]:
        try:
            # 새로운 키 형식에 맞게 패턴 검색
            pattern = f"mem:{user_id}:*"
            keys = self.client.keys(pattern)

            total = 0
            for key in keys:
                total += self.client.llen(key)

            return {
                "total_memories": total,
                "conversation_memories": None,
                "task_memories": None,
                "knowledge_memories": None,
                "avg_importance": None,
                "latest_memory": None,
            }
        except Exception as e:
            logger.error(f"Redis get_memory_stats failed: {e}")
            return {}

    def get_recent_memories(
        self,
        user_id: int,
        agent_id: int,
        limit: int = 5,
        session_id: Optional[str] = None,
        current_date_only: bool = False,
    ) -> List[Dict[str, Any]]:
        try:
            # 새로운 키 형식에 맞게 패턴 검색
            if current_date_only:
                # 현재 날짜의 메모리만 조회
                today = datetime.now().strftime("%Y-%m-%d")
                if session_id:
                    pattern = f"mem:{user_id}:{today}:{session_id}"
                else:
                    pattern = f"mem:{user_id}:{today}:*"
            else:
                # 모든 날짜의 메모리 조회
                if session_id:
                    # 특정 세션의 메모리 조회: mem:{user_id}:*:{session_id}
                    pattern = f"mem:{user_id}:*:{session_id}"
                else:
                    # 모든 세션의 메모리 조회: mem:{user_id}:*
                    pattern = f"mem:{user_id}:*"

            # 패턴에 맞는 키들을 찾기
            keys = self.client.keys(pattern)

            if not keys:
                return []

            # 모든 키에서 메모리 수집
            all_memories = []
            for key in keys:
                values = self.client.lrange(key, 0, -1)
                for v in values:
                    try:
                        item = json.loads(v)
                        all_memories.append(item)
                    except Exception as e:
                        logger.warning(f"[REDIS] JSON 파싱 실패: {e}")
                        continue

            # timestamp 기준으로 정렬 (최신순)
            all_memories.sort(key=lambda x: x.get("created_timestamp", 0), reverse=False)

            # limit만큼 반환
            result = all_memories[:limit]
            return result
        except Exception as e:
            logger.error(f"Redis get_recent_memories failed: {e}")
            return []

    def get_agent_id_by_code(self, agent_code: str) -> Optional[int]:
        # Redis에서는 별도 스키마가 없으므로 None 반환 (상위에서 기본값 처리)
        return None

    def test_connection(self) -> bool:
        """Redis 연결 테스트"""
        try:
            self.client.ping()
            logger.info("[REDIS] 연결 테스트 성공")
            return True
        except Exception as e:
            logger.error(f"[REDIS] 연결 테스트 실패: {e}")
            return False

    def close(self):
        """Redis 연결 종료"""
        try:
            if self.client:
                self.client.close()
                logger.info("Redis 연결이 종료되었습니다.")
        except Exception as e:
            logger.error(f"Redis 연결 종료 중 오류: {e}")
        finally:
            self.client = None
