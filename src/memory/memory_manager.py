"""
Memory Manager

메모리 저장, 검색, 관리를 위한 중앙 관리자
"""

import logging
import os
import uuid
from enum import Enum
from logging import getLogger
from typing import Any, Dict, List, Optional, Tuple

from src.llm.interfaces import ChatMessage
from src.llm.interfaces.chat import MessageRole
from src.llm.manager import llm_manager
from src.prompts.prompt_manager import prompt_manager

from .providers.factory import MemoryProviderFactory

logger = getLogger("memory")

# 상수 정의
DEFAULT_MEMORY_PROVIDER = "mysql"
DEFAULT_MEMORY_TYPE = "conversation"
DEFAULT_IMPORTANCE = 1.0
DEFAULT_SOURCE = "inferred"
DEFAULT_CLEANUP_DAYS = 30
DEFAULT_LTM_LIMIT = 20
DEFAULT_STM_LIMIT = 5
DEFAULT_STM_MESSAGE_LIMIT = 1000
DEFAULT_STM_SUMMARY_LIMIT = 200
DEFAULT_PERSONAL_PROFILE_LIMIT = 50
DEFAULT_RECENT_MESSAGES_LIMIT = 3


class MemoryManager:
    """메모리 매니저"""

    def __init__(
        self, config: Optional[Dict[str, Any]] = None, init_immediately: bool = False
    ):
        """초기화 (주입형 구성 지원)

        Args:
            config: {"provider_type","database_url","redis_url"}
            init_immediately: True면 즉시 프로바이더 초기화
        """
        self._config: Optional[Dict[str, Any]] = config
        # 기본(장기/개인정보) 저장소 (예: MySQL)
        self.provider = None
        self.provider_type = None
        # 단기 메모리 저장소 (예: Redis)
        self.stm_provider = None
        if init_immediately:
            self._init_providers()

    def _init_providers(self):
        """메모리 프로바이더 초기화 (LTM: RDB, STM: Redis) - 주입형 구성 우선"""
        try:
            config = self._get_provider_config()
            self._init_ltm_provider(config)
            self._init_stm_provider(config)
        except Exception as e:
            logger.error(f"메모리 프로바이더 초기화 실패: {e}")

    def _get_provider_config(self) -> Dict[str, Any]:
        """프로바이더 설정 가져오기"""
        return {
            "provider_type": (self._config or {}).get("provider_type")
            or os.getenv("MEMORY_PROVIDER", DEFAULT_MEMORY_PROVIDER),
            "database_url": (self._config or {}).get("database_url")
            or os.getenv("DATABASE_URL"),
            "redis_url": (self._config or {}).get("redis_url")
            or os.getenv("REDIS_URL")
            or os.getenv("MEMORY_REDIS_URL"),
        }

    def _init_ltm_provider(self, config: Dict[str, Any]) -> None:
        """LTM 프로바이더 초기화"""
        if not config["database_url"]:
            logger.warning(
                "DATABASE_URL이 설정되지 않았습니다. 메모리 기능이 제한됩니다."
            )
            return

        if config["provider_type"].lower() == "mysql":
            self._init_mysql_provider(config["database_url"])
        else:
            logger.warning(
                f"지원하지 않는 메모리 프로바이더: {config['provider_type']}"
            )

    def _init_mysql_provider(self, database_url: str) -> None:
        """MySQL 프로바이더 초기화"""
        try:
            config = MemoryProviderFactory.get_mysql_config_from_url(database_url)
            factory = MemoryProviderFactory()
            provider_config = {"provider": "mysql", **config}
            self.provider = factory.create_provider(provider_config)

            if self.provider:
                self.provider_type = "mysql"
            else:
                logger.error("MySQL 메모리 프로바이더 생성에 실패했습니다.")
        except Exception as e:
            logger.error(f"MySQL 프로바이더 초기화 실패: {e}")

    def _init_stm_provider(self, config: Dict[str, Any]) -> None:
        """STM 프로바이더 초기화"""
        if not config["redis_url"]:
            return

        try:
            factory = MemoryProviderFactory()
            self.stm_provider = factory.create_provider(
                {
                    "provider": "redis",
                    "redis_url": config["redis_url"],
                }
            )

            if self.stm_provider:
                pass
        except Exception as e:
            logger.warning(f"Redis STM 프로바이더 초기화 실패: {e}")

    async def save_memory(
        self,
        user_id: int,
        content: str,
        memory_type: str = DEFAULT_MEMORY_TYPE,
        importance: float = DEFAULT_IMPORTANCE,
        agent_id: int | None = None,
        category: Optional[str] = None,
        source: Optional[str] = None,
    ) -> bool:
        """메모리 저장"""
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return False

        try:
            metadata = self._build_memory_metadata(
                memory_type, importance, agent_id, category, source
            )

            result = await self.provider.save_memory(user_id, content, metadata)
            self._log_save_result(result, user_id, memory_type, category)
            return result
        except Exception as e:
            logger.error(f"메모리 저장 중 오류 발생: {e}")
            return False

    def _build_memory_metadata(
        self,
        memory_type: str,
        importance: float,
        agent_id: Optional[int],
        category: Optional[str],
        source: Optional[str],
    ) -> Dict[str, Any]:
        """메모리 메타데이터 구성"""
        metadata = {
            "memory_type": memory_type,
            "importance": importance,
        }

        if agent_id is not None:
            metadata["agent_id"] = agent_id
        if category:
            metadata["category"] = category
        if source:
            src = str(source).lower()
            metadata["source"] = "fact" if src == "fact" else DEFAULT_SOURCE

        return metadata

    def _log_save_result(
        self, result: bool, user_id: int, memory_type: str, category: Optional[str]
    ) -> None:
        """메모리 저장 결과 로깅"""
        if not result:
            logger.warning(
                f"[MEMORY_MANAGER] 메모리 저장 실패: user_id={user_id}, type={memory_type}, category={category}"
            )

    def search_memories(
        self, user_id: int, agent_id: int, limit: int = 10, threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """메모리 검색"""
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return []

        try:
            return self.provider.search_memories(user_id, agent_id, limit, threshold)
        except Exception as e:
            logger.error(f"메모리 검색 중 오류 발생: {e}")
            return []

    # ------------------------
    # LTM (Long-Term Memory)
    # ------------------------
    def save_ltm(
        self,
        user_id: int,
        content: str,
        categories: Optional[List[str]] = None,
        agent_id: Optional[int] = None,
        importance: float = DEFAULT_IMPORTANCE,
        memory_type: Optional[str] = None,
        source: str = DEFAULT_SOURCE,
    ) -> bool:
        """장기 메모리(LTM) 저장"""
        if not self.provider:
            logger.warning("기본 프로바이더가 초기화되지 않았습니다. LTM 저장 불가.")
            return False

        if not self._is_valid_ltm_type(memory_type):
            return False

        try:
            if categories:
                return self._save_ltm_with_categories(
                    user_id,
                    content,
                    categories,
                    agent_id,
                    importance,
                    memory_type,
                    source,
                )
            else:
                return self._save_ltm_single(
                    user_id, content, agent_id, importance, memory_type, source
                )
        except Exception as e:
            logger.error(f"LTM 저장 중 오류 발생: {e}")
            return False

    def _is_valid_ltm_type(self, memory_type: Optional[str]) -> bool:
        """LTM 타입 유효성 검사"""
        valid_types = ("long_term_memory", "semantic", "episodic", "procedural")
        if not memory_type or memory_type not in valid_types:
            logger.warning(
                f"유효하지 않은 LTM memory_type: {memory_type}. 허용값: {'|'.join(valid_types)}"
            )
            return False
        return True

    def _save_ltm_with_categories(
        self,
        user_id: int,
        content: str,
        categories: List[str],
        agent_id: Optional[int],
        importance: float,
        memory_type: str,
        source: str,
    ) -> bool:
        """다중 카테고리 LTM 저장"""
        saved_any = False
        for cat in categories:
            metadata = self._build_memory_metadata(
                memory_type, importance, agent_id, str(cat), source
            )
            ok = self.provider.save_memory(user_id, content, metadata=metadata)
            saved_any = saved_any or ok
        return saved_any

    def _save_ltm_single(
        self,
        user_id: int,
        content: str,
        agent_id: Optional[int],
        importance: float,
        memory_type: str,
        source: str,
    ) -> bool:
        """단일 LTM 저장"""
        metadata = self._build_memory_metadata(
            memory_type, importance, agent_id, None, source
        )
        return self.provider.save_memory(user_id, content, metadata=metadata)

    def list_ltm(
        self, user_id: int, agent_id: int, limit: int = DEFAULT_LTM_LIMIT
    ) -> List[Dict[str, Any]]:
        """최근 LTM 조회 (서술형 특징). 기본 저장소에서 조회 후 필터링."""
        if not self.provider:
            return []
        try:
            items = self.provider.get_recent_memories(user_id, agent_id, limit * 2)
            return self._filter_ltm_items(items, limit)
        except Exception as e:
            logger.error(f"LTM 조회 중 오류 발생: {e}")
            return []

    def _filter_ltm_items(
        self, items: List[Dict[str, Any]], limit: int
    ) -> List[Dict[str, Any]]:
        """LTM 아이템 필터링"""
        # allowed_types = {"long_term_memory", "semantic", "episodic", "procedural"}
        allowed_types = {
            "long_term_memory"
        }  # ⚠️ semantic, episodic, procedural 비활성화
        filtered = []

        for item in items:
            if item.get("memory_type") in allowed_types and str(
                item.get("category") or ""
            ).lower() not in ("personal",):
                filtered.append(item)

        return filtered[:limit]

    # ------------------------
    # STM (Short-Term Memory)
    # ------------------------

    def get_all_session_messages(
        self, user_id: int, agent_id: int, session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """세션 전체 메시지 조회"""
        if not self.stm_provider:
            return []
        try:
            return self.stm_provider.get_recent_memories(
                user_id,
                agent_id,
                limit=DEFAULT_STM_MESSAGE_LIMIT,
                session_id=session_id,
            )
        except Exception as e:
            logger.error(f"세션 전체 메시지 조회 중 오류 발생: {e}")
            return []

    def save_stm_message(
        self,
        user_id: int,
        content: Dict[str, str],
        agent_id: int,
        session_id: Optional[str] = None,
    ) -> bool:
        """단기 메모리: 세션 내 최근 메시지를 Redis에 저장"""
        logger.debug(
            f"[MEMORY_MANAGER] save_stm_message 호출 - user_id={user_id}, agent_id={agent_id}, session_id={session_id}, "
            f"content_keys={list(content.keys()) if content else None}, "
            f"user_content_len={len(content.get('user', '')) if content else 0}, "
            f"bot_content_len={len(content.get('bot', '')) if content else 0}"
        )
        
        if not self.stm_provider:
            logger.warning("[MEMORY_MANAGER] STM 프로바이더가 초기화되지 않았습니다.")
            return False

        if not self._test_stm_connection():
            logger.error("[MEMORY_MANAGER] Redis 연결 테스트 실패")
            return False

        session_id = self._ensure_session_id(session_id, "STM 메시지 저장")
        logger.debug(f"[MEMORY_MANAGER] 세션 ID 확인 완료: {session_id}")

        try:
            logger.debug(
                f"[MEMORY_MANAGER] stm_provider.save_memory 호출 - user_id={user_id}, agent_id={agent_id}, session_id={session_id}"
            )
            result = self.stm_provider.save_memory(
                user_id=user_id,
                content=content,
                metadata={
                    "memory_type": "messages",
                    "agent_id": agent_id,
                    "session_id": session_id,
                },
            )
            if not result:
                logger.error(
                    f"[MEMORY_MANAGER] 메시지 저장 실패: user_id={user_id}, agent_id={agent_id}, session_id={session_id}"
                )
            else:
                logger.info(
                    f"[MEMORY_MANAGER] 메시지 저장 성공: user_id={user_id}, agent_id={agent_id}, session_id={session_id}"
                )
            return result
        except Exception as e:
            logger.error(f"[MEMORY_MANAGER] STM 메시지 저장 중 오류 발생: {e}", exc_info=True)
            return False

    def _ensure_session_id(self, session_id: Optional[str], operation: str) -> str:
        """세션 ID 보장 (없으면 생성)"""
        if not session_id:
            session_id = str(uuid.uuid4())
        return session_id

    def save_stm_summary(
        self,
        user_id: int,
        summary: str,
        agent_id: int,
        session_id: Optional[str] = None,
    ) -> bool:
        """단기 메모리: 해당 세션(또는 최근 대화) 요약을 Redis에 저장"""
        if not self.stm_provider:
            logger.warning("STM 프로바이더가 초기화되지 않았습니다.")
            return False

        if not self._test_stm_connection():
            logger.error("[STM] Redis 연결 테스트 실패")
            return False

        session_id = self._ensure_session_id(session_id, "STM 요약 저장")

        try:
            result = self.stm_provider.save_memory(
                user_id=user_id,
                content=summary,
                metadata={
                    "memory_type": "summary",
                    "agent_id": agent_id,
                    "session_id": session_id,
                },
            )
            if not result:
                logger.error(
                    f"[STM] 요약 저장 실패: user_id={user_id}, agent_id={agent_id}"
                )
            return result
        except Exception as e:
            logger.error(f"STM 요약 저장 중 오류 발생: {e}")
            return False

    def get_stm_recent_messages(
        self,
        user_id: int,
        agent_id: int,
        k: int = DEFAULT_RECENT_MESSAGES_LIMIT,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """최근 STM 메시지 k개 반환 (Redis)"""
        if not self.stm_provider:
            logger.warning("[STM] STM 프로바이더가 초기화되지 않았습니다.")
            return []

        if not self._test_stm_connection():
            logger.error("[STM] Redis 연결 테스트 실패")
            return []

        try:
            limit = max(k * 5, 50)

            # Redis 키 존재 여부 확인 (새로운 키 형식에 맞게 패턴 검색)
            if hasattr(self.stm_provider, "client"):
                if session_id:
                    pattern = f"mem:{user_id}:*:{session_id}"
                else:
                    pattern = f"mem:{user_id}:*"
                keys = self.stm_provider.client.keys(pattern)
                if not keys:
                    return []

            values = self.stm_provider.get_recent_memories(
                user_id, agent_id, limit=limit, session_id=session_id, current_date_only=True
            )

            msgs = [v for v in values if v.get("memory_type") == "messages"]

            result = [msg["content"] for msg in msgs[-k:]]  # chat_history 포맷팅
            return result
        except Exception as e:
            logger.error(f"STM 최근 메시지 조회 중 오류 발생: {e}")
            return []

    def _test_stm_connection(self) -> bool:
        """STM 연결 테스트"""
        if hasattr(self.stm_provider, "test_connection"):
            if not self.stm_provider.test_connection():
                logger.error("[STM] Redis 연결 실패")
                return False
        return True

    async def summarize_session(
        self, user_id: int, agent_id: int, session_id: Optional[str] = None
    ) -> Optional[str]:
        """세션 전체 대화 요약 생성 및 저장 (STM summary)."""
        try:
            messages = self.get_all_session_messages(
                user_id, agent_id, session_id=session_id
            )
            if not messages:
                return None
            # 대화 텍스트 구성 (최근 순서 유지)
            lines = []
            for m in messages:
                role = str(m.get("role") or "user").lower()
                content = str(m.get("content") or "")
                prefix = (
                    "User"
                    if role in ("user",)
                    else ("AI" if role in ("assistant", "ai") else role)
                )
                lines.append(f"{prefix}: {content}")
            conversation_text = "\n".join(lines)

            prompt = prompt_manager.render_template(
                "caia/caia_session_summary.j2", {"conversation_text": conversation_text}
            )
            lm_messages = [ChatMessage(role=MessageRole.USER, content=prompt)]
            resp = await llm_manager.chat(lm_messages)
            summary = resp.content.strip()
            # STM 요약 저장
            self.save_stm_summary(
                user_id=user_id,
                summary=summary,
                agent_id=agent_id,
                session_id=session_id,
            )
            return summary
        except Exception as e:
            logger.error(f"세션 요약 생성 실패: {e}")
            return None

    def get_stm_summary(
        self, user_id: int, agent_id: int, session_id: Optional[str] = None
    ) -> Optional[str]:
        """가장 최근 STM 요약 텍스트를 반환"""
        if not self.stm_provider:
            logger.warning("[STM] STM 프로바이더가 초기화되지 않았습니다.")
            return None

        if not self._test_stm_connection():
            logger.error("[STM] Redis 연결 테스트 실패")
            return None

        try:
            # Redis 키 존재 여부 확인 (새로운 키 형식에 맞게 패턴 검색)
            if hasattr(self.stm_provider, "client"):
                if session_id:
                    pattern = f"mem:{user_id}:*:{session_id}"
                else:
                    pattern = f"mem:{user_id}:*"
                keys = self.stm_provider.client.keys(pattern)
                if not keys:
                    return None

            values = self.stm_provider.get_recent_memories(
                user_id,
                agent_id,
                limit=DEFAULT_STM_SUMMARY_LIMIT,
                session_id=session_id,
            )

            for v in reversed(values):
                if v.get("memory_type") == "summary":
                    summary = str(v.get("content", ""))
                    return summary
            return None
        except Exception as e:
            logger.error(f"STM 요약 조회 중 오류 발생: {e}")
            return None

    # ------------------------
    # Personal Information (PII-like factual profile)
    # ------------------------
    def save_personal_fact(
        self, user_id: int, content: str, agent_id: Optional[int] = None
    ) -> bool:
        """개인정보(업무 기반 사실: 조직도/역할 등)를 저장. 기본 저장소 사용."""
        if not self.provider:
            logger.warning(
                "기본 프로바이더가 초기화되지 않았습니다. 개인정보 저장 불가."
            )
            return False
        try:
            metadata: Dict[str, Any] = {
                "memory_type": "semantic",
                "category": "personal",
            }
            if agent_id is not None:
                metadata["agent_id"] = agent_id
            return self.provider.save_memory(user_id, content, metadata=metadata)
        except Exception as e:
            logger.error(f"개인정보 저장 중 오류 발생: {e}")
            return False

    def get_personal_profile(
        self, user_id: int, agent_id: int, limit: int = DEFAULT_PERSONAL_PROFILE_LIMIT
    ) -> List[Dict[str, Any]]:
        """개인정보 항목 목록 조회"""
        if not self.provider:
            return []
        try:
            items = self.provider.get_recent_memories(user_id, agent_id, limit)

            # 개인정보 관련 카테고리 목록 정의
            personal_categories = {
                "personal",
                "인사정보",
                "경력정보",
                "프로젝트",
                "주업무",
                "개인정보",
                "프로필",
                "identity",
                "profile",
                "career",
                "project",
                "work",
                "직무",
                "조직",
                "위치",
                "연락처",
            }

            # 카테고리가 개인정보 관련인지 확인하는 함수
            def is_personal_category(category):
                if not category:
                    return False
                category_lower = str(category).lower().strip()
                return category_lower in personal_categories

            personal_items = [
                m for m in items if is_personal_category(m.get("category"))
            ]

            return personal_items
        except Exception as e:
            logger.error(f"개인정보 조회 중 오류 발생: {e}")
            return []

    # ------------------------
    # Aggregation for personalization
    # ------------------------
    def get_personalized_context(
        self,
        user_id: int,
        agent_id: int,
        k_recent: int = DEFAULT_RECENT_MESSAGES_LIMIT,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """개인화된 답변 생성을 위한 컨텍스트 번들 반환"""
        return {
            "personal_profile": self.get_personal_profile(user_id, agent_id),
            "ltm_traits": self.list_ltm(user_id, agent_id),
            "stm_summary": self.get_stm_summary(
                user_id, agent_id, session_id=session_id
            ),
            "stm_recent_messages": self.get_stm_recent_messages(
                user_id, agent_id, k_recent, session_id=session_id
            ),
        }

    def update_memory_access(self, memory_id: int) -> bool:
        """메모리 접근 시간 업데이트

        Args:
            memory_id: 메모리 ID

        Returns:
            업데이트 성공 여부
        """
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return False

        try:
            return self.provider.update_memory_access(memory_id)
        except Exception as e:
            logger.error(f"메모리 접근 시간 업데이트 중 오류 발생: {e}")
            return False

    def delete_memory(self, memory_id: int, user_id: int) -> bool:
        """메모리 삭제

        Args:
            memory_id: 메모리 ID
            user_id: 사용자 ID

        Returns:
            삭제 성공 여부
        """
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return False

        try:
            return self.provider.delete_memory(memory_id, user_id)
        except Exception as e:
            logger.error(f"메모리 삭제 중 오류 발생: {e}")
            return False

    def delete_memories_by_category(
        self, user_id: int, agent_id: int, category: str, memory_type: str
    ) -> bool:
        """카테고리별 메모리 삭제

        Args:
            user_id: 사용자 ID
            agent_id: 에이전트 ID
            category: 카테고리
            memory_type: 메모리 타입

        Returns:
            삭제 성공 여부
        """
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return False

        try:
            return self.provider.delete_memories_by_category(
                user_id, agent_id, category, memory_type
            )
        except Exception as e:
            logger.error(f"카테고리별 메모리 삭제 중 오류 발생: {e}")
            return False

    def cleanup_old_memories(self, days: int = DEFAULT_CLEANUP_DAYS) -> int:
        """오래된 메모리 정리"""
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return 0

        try:
            return self.provider.cleanup_old_memories(days)
        except Exception as e:
            logger.error(f"메모리 정리 중 오류 발생: {e}")
            return 0

    def get_memory_stats(self, user_id: int) -> Dict[str, Any]:
        """메모리 통계 조회

        Args:
            user_id: 사용자 ID

        Returns:
            메모리 통계 정보
        """
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return {}

        try:
            return self.provider.get_memory_stats(user_id)
        except Exception as e:
            logger.error(f"메모리 통계 조회 중 오류 발생: {e}")
            return {}

    def get_recent_memories(
        self, user_id: int, agent_id: int, limit: int = DEFAULT_STM_LIMIT
    ) -> List[Dict[str, Any]]:
        """최근 메모리 조회 (에이전트 스코프)"""
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return []
        try:
            return self.provider.get_recent_memories(user_id, agent_id, limit)
        except Exception as e:
            logger.error(f"최근 메모리 조회 중 오류 발생: {e}")
            return []

    def get_provider_info(self) -> Dict[str, Any]:
        """프로바이더 정보 조회

        Returns:
            프로바이더 정보
        """
        return {
            "provider_type": self.provider_type,
            "is_available": self.provider is not None,
            "status": "active" if self.provider else "unavailable",
            "stm_available": self.stm_provider is not None,
            "configured": bool(self._config),
        }

    def get_agent_id_by_code(self, agent_code: str) -> Optional[int]:
        """에이전트 코드로 agent_id 조회"""
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return None
        try:
            return self.provider.get_agent_id_by_code(agent_code)
        except Exception as e:
            logger.error(f"에이전트 조회 중 오류 발생: {e}")
            return None

    def get_agent_info_by_code(self, agent_code: str) -> Optional[Dict[str, Any]]:
        """에이전트 코드로 에이전트 정보 조회"""
        if not self.provider:
            logger.warning("메모리 프로바이더가 초기화되지 않았습니다.")
            return None
        try:
            return self.provider.get_agent_info_by_code(agent_code)
        except Exception as e:
            if "SELECT command denied" in str(e):
                logger.warning(f"에이전트 정보 조회 권한 없음: {e}")
            else:
                logger.error(f"에이전트 정보 조회 중 오류 발생: {e}")
            return None

    def close(self):
        """메모리 매니저 종료"""
        if self.provider:
            self.provider.close()
        if self.stm_provider:
            try:
                self.stm_provider.close()
            except Exception:
                pass


def _config_from_env() -> Dict[str, Any]:
    """환경변수에서 설정 가져오기"""
    return {
        "provider_type": os.getenv("MEMORY_PROVIDER", DEFAULT_MEMORY_PROVIDER),
        "database_url": os.getenv("DATABASE_URL"),
        "redis_url": os.getenv("REDIS_URL") or os.getenv("MEMORY_REDIS_URL"),
    }


def create_memory_manager(config: Optional[Dict[str, Any]] = None) -> "MemoryManager":
    mm = MemoryManager(config=config, init_immediately=bool(config))
    return mm


# 전역 인스턴스 (지연 초기화)
memory_manager = MemoryManager(init_immediately=False)


def initialize_memory_manager(config: Optional[Dict[str, Any]] = None) -> None:
    memory_manager._config = config or _config_from_env()
    memory_manager._init_providers()
