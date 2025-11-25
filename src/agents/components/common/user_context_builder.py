"""
User Context Builder Component

사용자 컨텍스트를 세분화된 메모리 구조로 구성하는 컴포넌트
"""

from logging import getLogger
from typing import Any, Dict, List, Optional

from src.database.services.user_services import UserService
from src.utils.db_utils import get_db_session
from src.memory.memory_manager import MemoryManager

logger = getLogger("agents.user_context_builder")


class UserContextBuilder:
    """사용자 컨텍스트 빌더"""

    def __init__(self, memory_manager: MemoryManager):
        """
        초기화

        Args:
            memory_manager: 메모리 매니저 인스턴스
        """
        self.memory_manager = memory_manager

    async def build_user_context(
        self,
        user_id: int,
        agent_id: int,
        session_id: Optional[str] = None,
        k_recent: int = 3,
        semantic_limit: int = 10,
        episodic_limit: int = 5,
        procedural_limit: int = 3,
        personal_limit: int = 10,
    ) -> Dict[str, Any]:
        """
        세분화된 사용자 컨텍스트를 구성합니다.

        Args:
            user_id: 사용자 ID
            agent_id: 에이전트 ID
            session_id: 세션 ID (선택적)
            k_recent: 최근 대화 개수
            semantic_limit: Semantic 메모리 개수
            episodic_limit: Episodic 메모리 개수
            procedural_limit: Procedural 메모리 개수
            personal_limit: 개인정보 개수

        Returns:
            세분화된 사용자 컨텍스트
        """
        try:
            logger.info(
                f"[USER_CONTEXT] 사용자 컨텍스트 빌더 시작: user_id={user_id}, agent_id={agent_id}, session_id={session_id}"
            )

            # 1. 최근 대화 k개 (단기기억)
            logger.info(f"[USER_CONTEXT] Step 1: 최근 대화 조회 (limit={k_recent})")

            # STM 프로바이더 상태 확인
            if not self.memory_manager.stm_provider:
                logger.warning(
                    "[USER_CONTEXT] STM 프로바이더가 초기화되지 않았습니다. STM 메모리 로딩을 건너뜁니다."
                )
                recent_messages = []
            else:
                # logger.info(
                #     "[USER_CONTEXT] STM 프로바이더가 초기화되었습니다. 최근 메시지 조회를 시작합니다."
                # )
                recent_messages = self.memory_manager.get_stm_recent_messages(
                    user_id=user_id,
                    agent_id=agent_id,
                    k=k_recent,
                    session_id=session_id,
                )
                logger.info(
                    f"[USER_CONTEXT] Step 1: 최근 메시지 조회 완료: {recent_messages}"
                )

            # # 2. 해당 세션 요약 (단기기억)
            # logger.debug(f"[USER_CONTEXT] Step 2: 세션 요약 조회")
            # if not self.memory_manager.stm_provider:
            #     logger.warning(
            #         "[USER_CONTEXT] STM 프로바이더가 초기화되지 않았습니다. 세션 요약 조회를 건너뜁니다."
            #     )
            #     session_summary = None
            # else:
            #     session_summary = self.memory_manager.get_stm_summary(
            #         user_id=user_id, agent_id=agent_id, session_id=session_id
            #     )
            # logger.info(
            #     f"[USER_CONTEXT] Step 2: 단기 메모리 요약 조회 완료: {'Found' if session_summary else 'None'}"
            # )
            # TEMP: session_summary 비활성화
            session_summary = None

            # 3. Semantic 메모리 (장기기억) - 일반 지식 + 개인정보 포함
            logger.info(
                f"[USER_CONTEXT] Step 3: 장기 메모리 조회 (limit={semantic_limit + personal_limit})"
            )
            all_memories = self.memory_manager.get_recent_memories(
                user_id=user_id,
                agent_id=agent_id,
                limit=semantic_limit + personal_limit,
            )
            logger.debug(
                f"[USER_CONTEXT] Step 3: 모든 메모리 조회 완료: {len(all_memories)}개"
            )

            # 개인정보 관련 카테고리 목록 정의
            personal_categories = {
                "인사정보",
            }

            def is_personal_category(category):
                if not category:
                    return False
                category_lower = str(category).lower().strip()
                return category_lower in personal_categories

            # 개인정보 메모리만 추출 (semantic, episodic, procedural 비활성화)
            personal_memories = []

            for m in all_memories:
                if m.get("memory_type") == "semantic" and is_personal_category(
                    m.get("category")
                ):
                    personal_memories.append(m)

            logger.debug(
                f"[USER_CONTEXT] Step 3a: 개인정보 메모리 추출: {len(personal_memories)}개"
            )

            # 개인정보 컨텍스트 별도 추출
            personal_info = {
                "personal_memories": [
                    {
                        "content": m.get("content"),
                        "category": m.get("category"),
                        "importance": m.get("importance"),
                    }
                    for m in personal_memories
                ],
                "has_personal_data": len(personal_memories) > 0,
                "personal_categories": list(
                    set(
                        m.get("category")
                        for m in personal_memories
                        if m.get("category")
                    )
                ),
            }
            logger.debug(
                f"[USER_CONTEXT] Step 3d: 개인정보 컨텍스트 추출 완료: {len(personal_memories)}개"
            )

            # 4. LTM 메모리 조회 (기존 장기 메모리)
            logger.debug(f"[USER_CONTEXT] Step 4: LTM 메모리 조회")
            ltm_memories = self.memory_manager.list_ltm(
                user_id=user_id, agent_id=agent_id, limit=10
            )

            # LTM 메모리를 문자열로 변환
            long_term_memories = ""
            if ltm_memories:
                ltm_contents = []
                for memory in ltm_memories:
                    content = memory.get("content", "").strip()
                    if content:
                        ltm_contents.append(content)
                long_term_memories = "\n".join(ltm_contents)

            logger.info(
                f"[USER_CONTEXT] Step 4: LTM 메모리 조회 완료: {len(ltm_memories)}개, 내용 길이: {len(long_term_memories)}"
            )

            # Episodic, Procedural 메모리 비활성화
            episodic_memories = []
            procedural_memories = []

            # 사용자 정보에서 sso_id (user_id 필드) 가져오기
            sso_id = None
            try:
                with get_db_session() as db:
                    user_service = UserService()
                    user = user_service.get_by_id(db, user_id)
                    if user and user.user_id:
                        sso_id = user.user_id  # user_id 필드를 sso_id로 사용
                        logger.debug(
                            f"[USER_CONTEXT] 사용자 SSO ID 설정: {sso_id} (username: {user.username})"
                        )
                    else:
                        logger.warning(
                            f"[USER_CONTEXT] 사용자 정보를 찾을 수 없음: user_id={user_id}"
                        )
            except Exception as e:
                logger.error(f"[USER_CONTEXT] 사용자 정보 조회 실패: {e}")
                # 디버깅을 위해 추가 로그
                logger.error(
                    f"[USER_CONTEXT] 사용자 조회 시도: user_id={user_id}, type={type(user_id)}"
                )
            finally:
                if "db" in locals():
                    db.close()

            user_context = {
                # 단기기억 ⚠️ 포맷
                "recent_messages": recent_messages,
                "session_summary": session_summary,
                # 장기기억 (LTM)
                "long_term_memories": long_term_memories,
                # 개인정보 컨텍스트만 사용 (semantic, episodic, procedural 비활성화)
                "personal_info": personal_info,
                # MCP 도구용 SSO ID 추가
                "sso_id": sso_id,
            }

            logger.info(
                f"[USER_CONTEXT] 사용자 컨텍스트 빌더 완료: user_id={user_id}: "
                f"recent={len(recent_messages)}, "
                f"ltm={len(ltm_memories)}, "
                f"personal_info={len(personal_memories)}"
            )

            return user_context

        except Exception as e:
            logger.error(f"[USER_CONTEXT] 사용자 컨텍스트 빌더 실패: {e}")
            return {
                "recent_messages": [],
                "session_summary": None,
                "long_term_memories": "",
                "personal_info": {
                    "personal_memories": [],
                    "has_personal_data": False,
                    "personal_categories": [],
                },
            }

    async def search_memories(
        self,
        query: str,
        user_id: int,
        agent_id: int,
        memory_type: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        쿼리와 관련된 메모리를 검색합니다.

        Args:
            query: 검색할 쿼리
            user_id: 사용자 ID
            agent_id: 에이전트 ID
            memory_type: 메모리 타입 (선택적)
            limit: 반환할 최대 결과 수

        Returns:
            검색된 메모리 목록
        """
        logger.debug(
            f"[USER_CONTEXT] 메모리 검색 시작: user_id={user_id}, agent_id={agent_id}, query={query}, type={memory_type}"
            f"with query: {query}, type: {memory_type}"
        )
        try:
            return self.memory_manager.search_memories(
                user_id=user_id,
                agent_id=agent_id,
                limit=limit,
                memory_type=memory_type,
            )
        except Exception as e:
            logger.error(f"[USER_CONTEXT] 메모리 검색 실패: {e}")
            return []

    async def save_memory(
        self,
        content: str,
        user_id: int,
        agent_id: int,
        memory_type: str,
        categories: Optional[List[str]] = None,
        importance: float = 1.0,
    ) -> bool:
        """
        메모리를 저장합니다.

        Args:
            content: 저장할 내용
            user_id: 사용자 ID
            agent_id: 에이전트 ID
            memory_type: 메모리 타입
            categories: 카테고리 목록 (선택적)
            importance: 중요도 (기본 1.0)

        Returns:
            저장 성공 여부
        """
        logger.debug(
            f"[USER_CONTEXT] 메모리 저장 시작: user_id={user_id}, agent_id={agent_id}, type={memory_type}, importance={importance}"
            f"type={memory_type}, importance={importance}"
        )
        try:
            return self.memory_manager.save_ltm(
                user_id=user_id,
                content=content,
                categories=categories,
                agent_id=agent_id,
                importance=importance,
                memory_type=memory_type,
            )
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")
            return False
