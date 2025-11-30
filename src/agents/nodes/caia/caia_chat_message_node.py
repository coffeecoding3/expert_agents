"""
CAIA Chat Message Node

채팅 메시지를 데이터베이스에 저장하는 노드
일반 응답 및 토론 스크립트 저장 처리
"""

from logging import getLogger
from typing import Any, Callable, Dict, Optional

from langchain_core.messages import AIMessage
from sqlalchemy.orm import Session

from src.agents.components.discussion.discussion_message_storage import (
    DiscussionMessageStorage,
    prepare_message_metadata_with_topic_suggestions,
)
from src.database.connection import get_db
from src.database.services import (
    agent_service,
    chat_channel_service,
    chat_message_service,
)

logger = getLogger("agents.caia_chat_message_node")


class CAIAChatMessageNode:
    """CAIA 채팅 메시지 저장 노드"""

    def __init__(
        self,
        logger: Any,
        get_agent_id: Callable[[Dict[str, Any]], int],
    ):
        """
        초기화

        Args:
            logger: 로거
            get_agent_id: 에이전트 ID 조회 함수
        """
        self.logger = logger
        self.get_agent_id = get_agent_id
        # 토론 메시지 저장 모듈
        self.discussion_storage = DiscussionMessageStorage(logger_instance=logger)

    def _get_agent_code(self, db: Session, agent_id: int) -> str:
        """에이전트 코드 조회"""
        try:
            agent_code = agent_service.get_code_by_id(db, agent_id)
            return agent_code if agent_code else "caia"
        except Exception as e:
            self.logger.warning(f"에이전트 코드 조회 실패: {e}")
            return "caia"

    async def save_chat_message(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        채팅 메시지를 데이터베이스에 저장합니다.

        Args:
            state: 현재 상태

        Returns:
            저장된 메시지 ID 정보를 포함한 상태 업데이트
        """
        try:
            channel_id = state.get("channel_id")
            user_message_id = state.get("user_message_id")
            agent_id = self.get_agent_id(state)

            if not channel_id:
                self.logger.warning(
                    "[GRAPH] channel_id가 없어 메시지 저장을 건너뜁니다"
                )
                return {}

            # DB 세션 생성
            db: Optional[Session] = None
            try:
                db = next(get_db())
            except Exception as e:
                self.logger.error(f"[GRAPH] DB 세션 생성 실패: {e}")
                return {}

            try:
                agent_code = self._get_agent_code(db, agent_id)

                # 토론 스크립트가 있는 경우 DiscussionMessageStorage로 위임
                script = state.get("script")
                if script and isinstance(script, list) and len(script) > 0:
                    self.logger.info(
                        f"[GRAPH] 토론 스크립트를 DiscussionMessageStorage로 저장합니다: {len(script)}개 발언"
                    )
                    # 스크립트 내용 로깅 (디버깅용)
                    for i, speech in enumerate(script):
                        if isinstance(speech, dict) and "speaker" in speech:
                            self.logger.debug(
                                f"[GRAPH] 발언 {i + 1}: {speech.get('speaker', 'Unknown')} - {speech.get('speech', '')[:50]}..."
                            )
                    # DiscussionMessageStorage는 자체적으로 DB 세션을 관리하므로
                    # 여기서는 위임만 하고 DB 세션은 닫지 않음
                    result = await self.discussion_storage.save_discussion_script(
                        state=state,
                        script=script,
                    )
                    if result:
                        # 같은 channel_id의 모든 discussion 메시지(setup, speaker, wrap_up)를 조회하여 saved_message_ids에 추가
                        try:
                            from src.database.models.chat import ChatMessage

                            all_discussion_messages = (
                                db.query(ChatMessage)
                                .filter(
                                    ChatMessage.channel_id == channel_id,
                                    ChatMessage.message_metadata.isnot(None),
                                    ChatMessage.is_deleted == False,
                                )
                                .all()
                            )

                            # discussion_order가 있는 메시지들만 필터링하고 정렬
                            discussion_messages_with_order = []
                            for msg in all_discussion_messages:
                                if (
                                    msg.message_metadata
                                    and isinstance(msg.message_metadata, dict)
                                    and "discussion_order" in msg.message_metadata
                                ):
                                    order = msg.message_metadata.get(
                                        "discussion_order", 999999
                                    )
                                    discussion_messages_with_order.append(
                                        (order, msg.id)
                                    )

                            # discussion_order로 정렬하여 순서 보장
                            discussion_messages_with_order.sort(key=lambda x: x[0])
                            discussion_message_ids = [
                                msg_id for _, msg_id in discussion_messages_with_order
                            ]

                            # saved_message_ids에 모든 discussion 메시지 ID 추가
                            saved_ids = result.get("saved_message_ids", [])
                            # 중복 제거하면서 순서 유지
                            all_message_ids = list(
                                dict.fromkeys(discussion_message_ids + saved_ids)
                            )
                            result["saved_message_ids"] = all_message_ids

                            self.logger.info(
                                f"[GRAPH] 토론 스크립트 저장 완료: {len(all_message_ids)}개 메시지 (setup + speaker + wrap_up 포함)"
                            )
                        except Exception as e:
                            self.logger.warning(
                                f"[GRAPH] discussion 메시지 조회 중 오류 (기존 saved_message_ids 사용): {e}"
                            )
                            self.logger.info(
                                f"[GRAPH] 토론 스크립트 저장 완료: {len(result.get('saved_message_ids', []))}개 메시지 저장됨"
                            )

                        return result
                    else:
                        self.logger.warning(
                            "[GRAPH] 토론 스크립트 저장 결과가 비어있습니다"
                        )
                elif script:
                    self.logger.warning(
                        f"[GRAPH] 토론 스크립트가 비어있거나 잘못된 형식입니다: {type(script)}, 길이: {len(script) if isinstance(script, list) else 'N/A'}"
                    )

                # 일반 응답 저장
                else:
                    messages = state.get("messages", [])
                    if messages and len(messages) > 0:
                        # 마지막 메시지가 AIMessage인지 확인
                        last_message = messages[-1]
                        if isinstance(last_message, AIMessage):
                            content = last_message.content
                        elif hasattr(last_message, "content"):
                            content = last_message.content
                        else:
                            content = str(last_message)

                        if content and content.strip():
                            self.logger.info("[GRAPH] 일반 응답을 저장합니다")

                            # topic_suggestions는 content에 합치지 않고 별도로 처리
                            topic_suggestions = state.get("topic_suggestions", [])
                            final_content = content.strip()

                            # message_metadata에 topic_suggestions 포함 (공통 함수 사용)
                            base_metadata = {
                                "total_token": len(final_content.split()),
                                "model": ["expert_agent"],
                            }

                            # discussion_setting에서 저장한 topic, speakers, discussion_rules, tools를 metadata에 추가
                            topic = state.get("topic")
                            speakers = state.get("speakers")
                            if topic and speakers:
                                self.logger.info(
                                    f"[GRAPH] discussion_setting 정보를 metadata에 저장: topic={topic}, speakers={len(speakers)}명"
                                )
                                base_metadata["topic"] = topic
                                base_metadata["speakers"] = speakers
                                if state.get("discussion_rules"):
                                    base_metadata["discussion_rules"] = state.get(
                                        "discussion_rules"
                                    )
                                if state.get("tools"):
                                    base_metadata["tools"] = state.get("tools")
                            else:
                                self.logger.debug(
                                    f"[GRAPH] state에 topic/speakers가 없음: topic={topic}, speakers={speakers}"
                                )

                            message_metadata = (
                                prepare_message_metadata_with_topic_suggestions(
                                    base_metadata=base_metadata,
                                    topic_suggestions=topic_suggestions,
                                    logger_instance=self.logger,
                                )
                            )

                            # 일반 메시지 저장 (lgenie_sync는 별도 노드에서)
                            assistant_message = chat_message_service.create(
                                db,
                                channel_id=channel_id,
                                agent_id=agent_id,
                                message_type=agent_code,
                                content=final_content,
                                parent_message_id=user_message_id,
                                message_metadata=message_metadata,
                            )

                            if assistant_message:
                                chat_channel_service.update_last_message(db, channel_id)
                                self.logger.info(
                                    f"[GRAPH] 일반 응답 저장 완료: {assistant_message.id}"
                                )
                                return {
                                    "assistant_message_id": assistant_message.id,
                                    "saved_message_ids": [assistant_message.id],
                                }

                self.logger.warning("[GRAPH] 저장할 메시지가 없습니다")
                return {}

            finally:
                if db:
                    try:
                        db.close()
                    except Exception:
                        pass

        except Exception as e:
            self.logger.error(f"[GRAPH] 채팅 메시지 저장 중 오류: {e}")
            return {}
