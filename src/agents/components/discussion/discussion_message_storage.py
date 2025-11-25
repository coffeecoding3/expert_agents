"""
Discussion Message Storage
토론 메시지 저장을 위한 통합 모듈
setup, speakers, wrap_up 단계의 메시지를 통일된 방식으로 저장
"""

from datetime import datetime, timedelta
from logging import getLogger
from typing import Any, Dict, List, Optional

from src.database.services import (
    agent_service,
    chat_channel_service,
    chat_message_service,
)
from src.agents.components.discussion.discussion_utils import DISCUSSION_ROLE_HOST
from src.utils.db_utils import get_db_session

logger = getLogger("agents.discussion_message_storage")


def prepare_message_metadata_with_topic_suggestions(
    base_metadata: Dict[str, Any],
    topic_suggestions: Optional[List[str]],
    logger_instance=None,
) -> Dict[str, Any]:
    """
    topic_suggestions를 포함한 message_metadata를 준비합니다.
    
    Args:
        base_metadata: 기본 메타데이터 딕셔너리
        topic_suggestions: 토픽 제안 리스트 (선택사항)
        logger_instance: 로거 인스턴스 (선택사항)
    
    Returns:
        topic_suggestions가 포함된 메타데이터 딕셔너리
    """
    log = logger_instance or logger
    metadata = base_metadata.copy()
    
    if topic_suggestions and isinstance(topic_suggestions, list) and len(topic_suggestions) > 0:
        metadata["topic_suggestions"] = topic_suggestions
        log.info(f"[MESSAGE_METADATA] topic_suggestions 저장: {len(topic_suggestions)}개")
    
    return metadata


class DiscussionMessageStorage:
    """토론 메시지 저장 클래스"""

    def __init__(self, logger_instance=None):
        """
        초기화

        Args:
            logger_instance: 로거 인스턴스 (선택사항)
        """
        self.logger = logger_instance or logger

    async def save_host_setup_message(
        self,
        state: Dict[str, Any],
        host_script: str,
    ) -> Optional[int]:
        """
        Setup 단계의 host 메시지를 저장합니다.

        Args:
            state: 현재 상태 (channel_id, user_message_id, agent_id 포함)
            host_script: host가 말한 내용

        Returns:
            저장된 메시지 ID (실패 시 None)
        """
        if not host_script or not host_script.strip():
            self.logger.warning("[DISCUSSION_STORAGE] 저장할 setup 메시지가 없습니다")
            return None

        channel_id = state.get("channel_id")
        user_message_id = state.get("user_message_id")
        agent_id = state.get("agent_id", 1)

        if not channel_id:
            self.logger.warning(
                "[DISCUSSION_STORAGE] channel_id가 없어 setup 메시지 저장을 건너뜁니다"
            )
            return None

        try:
            with get_db_session() as db:
                # agent_code 조회하여 message_type 설정
                agent_code = agent_service.get_code_by_id(db, agent_id)
                if not agent_code:
                    self.logger.warning(
                        f"[DISCUSSION_STORAGE] agent_code 조회 실패 (agent_id={agent_id}), 기본값 'caia' 사용"
                    )
                    agent_code = "caia"

                # message_type을 {agent_code}_discussion_HOST 형식으로 설정
                message_type = f"{agent_code}_discussion_{DISCUSSION_ROLE_HOST}"

                # created_at을 명시적으로 설정하여 순서 보장
                # discussion_order 0이므로 현재 시간 사용
                base_time = datetime.now()

                # Setup 메시지 저장 (content에 speaker_name 접두사 추가)
                setup_message = chat_message_service.create_message(
                    db,
                    channel_id=channel_id,
                    agent_id=agent_id,
                    message_type=message_type,
                    content=f"{host_script.strip()}",
                    parent_message_id=user_message_id,
                    created_at=base_time,  # 명시적으로 시간 설정
                    message_metadata={
                        "total_token": len(host_script.split()),
                        "model": ["expert_agent"],
                        "speaker_name": DISCUSSION_ROLE_HOST,
                        "is_host": True,
                        "is_discussion": True,
                        "stage": "setup",
                        "discussion_order": 0,  # setup은 항상 첫 번째
                    },
                )

                if setup_message:
                    chat_channel_service.update_last_message(db, channel_id)
                    self.logger.info(
                        f"[DISCUSSION_STORAGE] Setup 메시지 저장 완료: {setup_message.id}"
                    )
                    return setup_message.id
                else:
                    self.logger.warning("[DISCUSSION_STORAGE] Setup 메시지 저장 실패")
                    return None

        except Exception as e:
            self.logger.error(f"[DISCUSSION_STORAGE] Setup 메시지 저장 중 오류: {e}")
            return None

    async def save_host_wrapup_message(
        self,
        state: Dict[str, Any],
        wrapup_content: str,
        topic_suggestions: Optional[List[str]] = None,
    ) -> Optional[int]:
        """
        Wrap-up 단계의 host 메시지를 저장합니다.

        Args:
            state: 현재 상태 (channel_id, user_message_id, agent_id 포함)
            wrapup_content: wrap-up 내용

        Returns:
            저장된 메시지 ID (실패 시 None)
        """
        if not wrapup_content or not wrapup_content.strip():
            self.logger.warning("[DISCUSSION_STORAGE] 저장할 wrap-up 메시지가 없습니다")
            return None

        channel_id = state.get("channel_id")
        user_message_id = state.get("user_message_id")
        agent_id = state.get("agent_id", 1)

        if not channel_id:
            self.logger.warning(
                "[DISCUSSION_STORAGE] channel_id가 없어 wrap-up 메시지 저장을 건너뜁니다"
            )
            return None

        try:
            with get_db_session() as db:
                # agent_code 조회하여 message_type 설정
                agent_code = agent_service.get_code_by_id(db, agent_id)
                if not agent_code:
                    self.logger.warning(
                        f"[DISCUSSION_STORAGE] agent_code 조회 실패 (agent_id={agent_id}), 기본값 'caia' 사용"
                    )
                    agent_code = "caia"

                # message_type을 {agent_code}_discussion_HOST 형식으로 설정
                message_type = f"{agent_code}_discussion_{DISCUSSION_ROLE_HOST}"

                script = state.get("script", [])
                script_length = len(script) if isinstance(script, list) else 0
                max_order_from_db = 0
                try:
                    from src.database.models.chat import ChatMessage

                    existing_messages = (
                        db.query(ChatMessage)
                        .filter(
                            ChatMessage.channel_id == channel_id,
                            ChatMessage.message_metadata.isnot(None),
                        )
                        .all()
                    )
                    for msg in existing_messages:
                        if (
                            msg.message_metadata
                            and isinstance(msg.message_metadata, dict)
                            and "discussion_order" in msg.message_metadata
                        ):
                            order = msg.message_metadata.get("discussion_order", 0)
                            if isinstance(order, int) and order > max_order_from_db:
                                max_order_from_db = order
                except Exception as e:
                    self.logger.warning(
                        f"[DISCUSSION_STORAGE] 최대 discussion_order 조회 실패: {e}"
                    )

                # script_length가 있으면 그것을 사용, 없으면 DB에서 조회한 값 사용
                # setup이 0이므로 script는 1부터 시작하므로 script_length가 마지막 순서
                wrapup_order = max(script_length, max_order_from_db) + 1

                self.logger.info(
                    f"[DISCUSSION_STORAGE] Wrap-up discussion_order 계산: script_length={script_length}, max_order_from_db={max_order_from_db}, wrapup_order={wrapup_order}"
                )

                # created_at을 명시적으로 설정하여 순서 보장
                # setup 메시지의 시간을 기준으로 script_length + 1초로 계산
                wrapup_time = datetime.now()
                try:
                    from src.database.models.chat import ChatMessage

                    # setup 메시지의 시간을 찾아서 기준으로 사용
                    base_time = None
                    setup_message = (
                        db.query(ChatMessage)
                        .filter(
                            ChatMessage.channel_id == channel_id,
                            ChatMessage.message_metadata.isnot(None),
                        )
                        .all()
                    )
                    for msg in setup_message:
                        if (
                            msg.message_metadata
                            and isinstance(msg.message_metadata, dict)
                            and msg.message_metadata.get("discussion_order") == 0
                        ):
                            base_time = msg.created_at
                            break

                    if base_time:
                        wrapup_time = base_time + timedelta(seconds=script_length + 1)
                    else:
                        # setup을 찾을 수 없으면 DB에서 최대 시간 찾기
                        max_time = None
                        for msg in setup_message:
                            if (
                                msg.message_metadata
                                and isinstance(msg.message_metadata, dict)
                                and "discussion_order" in msg.message_metadata
                            ):
                                if max_time is None or msg.created_at > max_time:
                                    max_time = msg.created_at
                        if max_time:
                            wrapup_time = max_time + timedelta(seconds=1)
                except Exception as e:
                    self.logger.warning(
                        f"[DISCUSSION_STORAGE] 시간 계산 실패: {e}, 현재 시간 사용"
                    )

                # message_metadata 준비 (topic_suggestions 포함)
                base_metadata = {
                    "total_token": len(wrapup_content.split()),
                    "model": ["expert_agent"],
                    "speaker_name": DISCUSSION_ROLE_HOST,
                    "is_host": True,
                    "is_discussion": True,
                    "stage": "wrapup",
                    "discussion_order": wrapup_order,  # script 다음 순서
                }
                message_metadata = prepare_message_metadata_with_topic_suggestions(
                    base_metadata=base_metadata,
                    topic_suggestions=topic_suggestions,
                    logger_instance=self.logger,
                )

                wrapup_message = chat_message_service.create_message(
                    db,
                    channel_id=channel_id,
                    agent_id=agent_id,
                    message_type=message_type,
                    content=f"{wrapup_content.strip()}",
                    parent_message_id=user_message_id,
                    created_at=wrapup_time,  # 명시적으로 시간 설정
                    message_metadata=message_metadata,
                )

                if wrapup_message:
                    chat_channel_service.update_last_message(db, channel_id)
                    self.logger.info(
                        f"[DISCUSSION_STORAGE] Wrap-up 메시지 저장 완료: {wrapup_message.id}"
                    )
                    return wrapup_message.id
                else:
                    self.logger.warning("[DISCUSSION_STORAGE] Wrap-up 메시지 저장 실패")
                    return None

        except Exception as e:
            self.logger.error(f"[DISCUSSION_STORAGE] Wrap-up 메시지 저장 중 오류: {e}")
            return None

    async def save_discussion_script(
        self,
        state: Dict[str, Any],
        script: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        토론 스크립트 전체를 저장합니다.

        Args:
            state: 현재 상태 (channel_id, user_message_id, agent_id 포함)
            script: 토론 스크립트 리스트 (각 항목은 {"speaker": str, "speech": str} 형식)

        Returns:
            저장된 메시지 ID 정보를 포함한 딕셔너리
            - assistant_message_id: 마지막 저장된 메시지 ID
            - saved_message_ids: 저장된 모든 메시지 ID 리스트
        """
        if not script or not isinstance(script, list) or len(script) == 0:
            self.logger.warning("[DISCUSSION_STORAGE] 저장할 토론 스크립트가 없습니다")
            return {}

        channel_id = state.get("channel_id")
        user_message_id = state.get("user_message_id")
        agent_id = state.get("agent_id", 1)

        if not channel_id:
            self.logger.warning(
                "[DISCUSSION_STORAGE] channel_id가 없어 토론 스크립트 저장을 건너뜁니다"
            )
            return {}

        try:
            with get_db_session() as db:
                # agent_code 조회 (service 사용)
                agent_code = agent_service.get_code_by_id(db, agent_id)
                if not agent_code:
                    self.logger.warning(
                        f"[DISCUSSION_STORAGE] agent_code 조회 실패 (agent_id={agent_id}), 기본값 'caia' 사용"
                    )
                    agent_code = "caia"
                self.logger.debug(f"[DISCUSSION_STORAGE] agent_code 조회: {agent_code}")

                # service를 사용하여 토론 스크립트 저장
                result = chat_message_service.save_discussion_script(
                    db=db,
                    channel_id=channel_id,
                    agent_id=agent_id,
                    user_message_id=user_message_id,
                    script=script,
                    agent_code=agent_code,
                )

                return result

        except Exception as e:
            self.logger.error(f"[DISCUSSION_STORAGE] 토론 스크립트 저장 중 오류: {e}")
            return {}
