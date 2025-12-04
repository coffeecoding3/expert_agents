"""
Chat Response Generator for Expert Agent Service

채팅 응답 생성 및 SSE 스트리밍 처리
"""

import asyncio
from logging import getLogger
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.orm import Session

from src.agents.components.caia.caia_discussion_intent_analyzer import (
    CAIADiscussionIntent,
)
from src.database.services import chat_channel_service, chat_message_service
from src.memory.memory_manager import memory_manager
from src.orchestration.states.caia_state import CAIAAgentState

from src.schemas.sse_response import AgentStatus, SSEResponse, MessageResponse
from src.utils.log_collector import collector
from .stream_manager import stream_manager
from src.schemas.raih_exceptions import (
    RAIHBusinessException,
    RAIHAuthorizationException,
    RAIHAuthenticationException,
)

logger = getLogger("chat")


class ChatResponseGenerator:
    """채팅 응답 생성기 - SSE 스트리밍 처리 (Expert Agents 지원)"""

    def __init__(self, agent_code: str):
        self.agent_code = agent_code
        self.orchestrator = None  # generate_response에서 설정됨
        self.start_time = None
        self.node_index = 0
        self.total_nodes = 0  # 오케스트레이터가 설정되면 업데이트됨
        self.node_start_time = None
        self.final_content = ""
        self.agent_name = "RAIH"  # 기본값
        self.agent_id = 2  # 기본값

        # 채팅방 관련 속성들
        self.channel_id: Optional[int] = None
        self.user_message_id: Optional[int] = None
        self.assistant_message_id: Optional[int] = None
        self.db: Optional[Session] = None
        self.actual_user_id: Optional[str] = None  # 실제 사용자 ID

        # Response handler 캐시
        self._response_handler: Optional[Any] = None

    async def generate_response(
        self,
        orchestrator,
        question: str,
        user_id: str,
        session_id: str | None = None,
        db: Session | None = None,
        client_id: str | None = None,
        tools: Optional[List[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """채팅 응답을 생성하고 SSE로 스트리밍합니다."""
        logger.debug("[CHAT_GENERATOR] generate_response 호출됨")
        from src.utils.timezone_utils import get_current_time_in_timezone

        # 오케스트레이터 설정
        self.orchestrator = orchestrator
        self.session_id = session_id  # session_id 저장
        self.db = db  # 데이터베이스 세션 저장

        # 스트림 연속성 처리
        if session_id:
            await self._handle_stream_continuity(session_id, user_id, client_id)

        try:
            if (
                hasattr(orchestrator, "workflow")
                and orchestrator.workflow
                and hasattr(orchestrator.workflow, "nodes")
            ):
                if orchestrator.workflow.nodes is not None:
                    self.total_nodes = len(orchestrator.workflow.nodes)
                else:
                    self.total_nodes = 1
            else:
                self.total_nodes = 1
        except Exception as e:
            logger.error(f"Error in total_nodes calculation: {e}")
            self.total_nodes = 1

        self.start_time = get_current_time_in_timezone().timestamp()

        # 에이전트 정보 설정
        await self._setup_agent_info()

        # 사용자 ID 매핑
        numeric_user_id, actual_user_id = await self._map_user_id(user_id)

        # 실제 사용자 ID를 인스턴스 변수로 저장
        self.actual_user_id = actual_user_id

        # 메시지 상태 준비
        messages = [HumanMessage(content=question)]

        # user context 로드
        from src.agents.components.common.user_context_builder import UserContextBuilder

        # 메모리 매니저 초기화 확인 및 강제 초기화
        if not memory_manager.stm_provider or not memory_manager.provider:
            logger.warning(
                "[CHAT_GENERATOR] 메모리 매니저가 초기화되지 않았습니다. 강제 초기화를 시도합니다."
            )
            from src.memory.memory_manager import initialize_memory_manager

            initialize_memory_manager()
            logger.debug("[CHAT_GENERATOR] 메모리 매니저 강제 초기화 완료")

        context_builder = UserContextBuilder(memory_manager)
        user_context = await context_builder.build_user_context(
            user_id=numeric_user_id,
            agent_id=self.agent_id,
            session_id=session_id or "",
        )

        initial_state = {
            "user_query": question,
            "messages": messages,
            "agent_id": self.agent_id,
            "user_id": numeric_user_id,
            "session_id": session_id or "",
            "actual_user_id": self.actual_user_id,
            "user_context": user_context,
            "tools": tools,  # 도구 목록 추가
            "channel_id": self.channel_id,  # 채팅 채널 ID
            "user_message_id": self.user_message_id,  # 사용자 메시지 ID
        }

        collector.log("recent_messages", user_context.get("recent_messages", ""))
        collector.log("long_term_memories", user_context.get("long_term_memories", ""))
        collector.log("personal_info", user_context.get("personal_info", ""))

        # 의도 분석을 INIT 전에 수행
        intent = await self._analyze_intent_early(initial_state)
        initial_state["intent"] = intent

        if self.agent_code == "caia":
            # 의도에 따른 INIT 응답 생성 (토론 시작 의도인 경우만 discussion INIT)
            if intent == CAIADiscussionIntent.START_DISCUSSION.value:
                init_response = await self._create_discussion_init()
                yield init_response
            else:
                init_response = await self._create_general_init()
                yield init_response
        else:
            init_response = await self._create_general_init()
            yield init_response

        try:
            # 의도 분석 및 워크플로우 실행
            logger.debug("[CHAT_GENERATOR] _process_workflow 호출 시작")

            # 스트림 제너레이터 설정
            if self.session_id:
                await self._set_stream_generator(
                    self._process_workflow(state=initial_state)
                )

            async for sse_data in self._process_workflow(
                state=initial_state,
            ):
                # 스트림 상태 업데이트
                await self._update_stream_state(current_node="processing")
                yield sse_data

        except (
            RAIHAuthorizationException,
            RAIHAuthenticationException,
            RAIHBusinessException,
        ) as e:
            error_response = await self._create_error_response(e)
            yield error_response
            # 완료 상태 응답
            completion_response = await self._create_completion_response()
            yield completion_response
            return

        except asyncio.CancelledError as e:
            logger.warning("[CHAT_GENERATOR] 워크플로우 실행이 취소되었습니다.")
            error_response = await self._create_error_response(e)
            yield error_response
            # 완료 상태 응답
            completion_response = await self._create_completion_response()
            yield completion_response
            return

        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 워크플로우 실행 중 오류: {e}")
            error_response = await self._create_error_response(e)
            yield error_response
            # 완료 상태 응답
            completion_response = await self._create_completion_response()
            yield completion_response
            return

        # 완료 상태 응답
        completion_response = await self._create_completion_response()
        yield completion_response

    async def _setup_agent_info(self):
        """에이전트 정보를 설정합니다."""
        logger.debug(f"[CHAT_ROUTER] agent_code: {self.agent_code}")
        logger.debug(
            f"[CHAT_ROUTER] memory_manager.provider: {memory_manager.provider}"
        )
        logger.debug(
            f"[CHAT_ROUTER] memory_manager.provider_type: {memory_manager.provider_type}"
        )

        # 1. 먼저 memory_manager를 통해 에이전트 정보 조회 시도
        try:
            agent_info = memory_manager.get_agent_info_by_code(self.agent_code)
            logger.debug(
                f"[CHAT_ROUTER] memory_manager에서 조회한 agent_info: {agent_info}"
            )
            if agent_info:
                self.agent_id = agent_info.get("id", 2)
                self.agent_name = agent_info.get("name", f"Agent ({self.agent_code})")
                logger.debug(
                    f"[CHAT_ROUTER] memory_manager에서 설정 완료 - agent_id: {self.agent_id}, agent_name: {self.agent_name}"
                )
                return
        except Exception as e:
            logger.warning(f"[CHAT_ROUTER] memory_manager 에이전트 정보 조회 실패: {e}")

        # 2. memory_manager 실패 시 직접 데이터베이스에서 조회
        try:
            from src.database.services import database_service

            if database_service.is_available():
                # agents 테이블에서 agent_code로 조회
                agent_record = database_service.select_one(
                    "agents",
                    "id, name, code, description, is_active",
                    "code = %s AND is_active = 1",
                    (self.agent_code,),
                )

                if agent_record:
                    self.agent_id = agent_record["id"]
                    self.agent_name = agent_record["name"]
                    logger.debug(
                        f"[CHAT_ROUTER] 데이터베이스에서 조회 성공 - agent_id: {self.agent_id}, agent_name: {self.agent_name}"
                    )
                    return
                else:
                    logger.warning(
                        f"[CHAT_ROUTER] agents 테이블에서 agent_code '{self.agent_code}'를 찾을 수 없음"
                    )
            else:
                logger.warning(f"[CHAT_ROUTER] 데이터베이스 서비스 사용 불가")
        except Exception as e:
            logger.error(f"[CHAT_ROUTER] 데이터베이스 에이전트 정보 조회 실패: {e}")

        # 3. 모든 조회 실패 시 기본값 사용
        self.agent_id = 1
        self.agent_name = f"Unknown Agent ({self.agent_code})"
        logger.warning(
            f"[CHAT_ROUTER] 모든 에이전트 정보 조회 실패, 기본값 사용 - agent_id: {self.agent_id}, agent_name: {self.agent_name}"
        )

    async def _create_discussion_init(self):
        """토론 전용 초기 상태 응답을 생성합니다."""
        return await SSEResponse.create_init_discussion().send()

    async def _create_general_init(self):
        """일반 워크플로우용 초기 상태 응답을 생성합니다."""
        return await SSEResponse.create_init_general().send()

    async def _analyze_intent_early(self, state):
        """INIT 전에 의도를 분석합니다."""
        try:
            # CAIA는 새로운 discussion intent analyzer 사용
            if self.agent_code == "caia":
                from src.agents.components.caia.caia_discussion_intent_analyzer import (
                    CAIADiscussionQueryAnalyzer,
                )

                query = state["user_query"]
                user_context = state.get("user_context", {})
                chat_history = (
                    user_context.get("recent_messages", []) if user_context else []
                )

                analyzer = CAIADiscussionQueryAnalyzer()
                analysis_result = await analyzer.analyze_intent(
                    query=query,
                    chat_history=chat_history,
                    user_context=user_context,
                )
                intent = analysis_result.get("intent")
            else:
                # 다른 에이전트들은 기존 서비스 사용
                from src.agents.services.agent_intent_service import AgentIntentService

                intent_service = AgentIntentService(self.agent_code)
                analysis_result = await intent_service.analyze_intent(state)
                intent = analysis_result.get("intent")

            logger.debug(
                f"[CHAT_GENERATOR] {self.agent_code} 초기 의도 분류 결과: {intent}"
            )
            collector.log("intent", intent)

            return intent
        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 초기 의도 분석 실패: {e}")
            # CAIA의 경우 기본값은 non_discussable
            if self.agent_code == "caia":
                return CAIADiscussionIntent.NON_DISCUSSABLE.value
            return "general"  # 기본값으로 일반 워크플로우 사용

    async def _map_user_id(self, user_id: str) -> tuple[int, str]:
        """사용자 ID를 숫자 ID와 실제 사용자 ID로 매핑합니다."""
        try:
            # 먼저 숫자인지 확인
            numeric_id = int(user_id)
            # 숫자 ID인 경우 데이터베이스에서 실제 사용자 ID 조회
            try:
                from src.database.services import database_service

                if database_service.is_available():
                    user_record = database_service.select_one(
                        "users", "user_id", "id = %s", (numeric_id,)
                    )
                    if user_record:
                        actual_user_id = user_record["user_id"]
                        logger.debug(
                            f"[CHAT] 사용자 ID 매핑: {numeric_id} -> {actual_user_id}"
                        )
                        return numeric_id, actual_user_id
                    else:
                        logger.warning(
                            f"[CHAT] 사용자를 찾을 수 없음: {numeric_id}, Unknown 사용"
                        )
                        return numeric_id, "Unknown"
                else:
                    logger.warning(
                        f"[CHAT] 데이터베이스 서비스 사용 불가, Unknown 사용"
                    )
                    return numeric_id, "Unknown"
            except Exception as e:
                logger.error(f"[CHAT] 사용자 ID 조회 실패: {e}, Unknown 사용")
                return numeric_id, "Unknown"
        except ValueError:
            # 문자열인 경우 데이터베이스에서 ID 조회
            try:
                from src.database.services import database_service

                if database_service.is_available():
                    user_record = database_service.select_one(
                        "users", "id, user_id", "user_id = %s", (user_id,)
                    )
                    if user_record:
                        numeric_user_id = user_record["id"]
                        actual_user_id = user_record["user_id"]
                        logger.debug(
                            f"[CHAT] 사용자 ID 매핑: {user_id} -> {numeric_user_id} ({actual_user_id})"
                        )
                        return numeric_user_id, actual_user_id
                    else:
                        logger.warning(
                            f"[CHAT] 사용자를 찾을 수 없음: {user_id}, Unknown 사용"
                        )
                        return 1, "Unknown"
                else:
                    logger.warning(
                        f"[CHAT] 데이터베이스 서비스 사용 불가, Unknown 사용"
                    )
                    return 1, "Unknown"
            except Exception as e:
                logger.error(f"[CHAT] 사용자 ID 매핑 실패: {e}, Unknown 사용")
                return 1, "Unknown"

    async def _process_workflow(self, state):
        """워크플로우를 처리합니다."""
        # 이미 분석된 의도 사용
        intent = state.get("intent", "general")

        logger.debug(
            f"[CHAT_GENERATOR] {self.agent_code} 워크플로우 처리 - 의도: {intent}"
        )

        # CAIA는 그래프 워크플로우에서 의도 분석 및 라우팅을 처리
        # discussion 의도는 SSE 스트리밍을 위해 별도 처리
        if self.agent_code == "caia":
            intent = state.get("intent")
            next_node = state.get("next_node")
            # next_node가 "discussion"이면 workflow 밖에서 처리 (start_discussion)
            # setup_discussion은 일반 워크플로우에서 처리 (message 반환)
            if (
                next_node == "discussion"
                or intent == CAIADiscussionIntent.START_DISCUSSION.value
            ):
                # discussion은 workflow 밖에서 처리 (SSE 스트리밍)
                logger.debug(
                    f"[CHAT_GENERATOR] CAIA - start_discussion 의도 감지, 별도 처리"
                )
                async for sse_data in self._handle_special_workflow(
                    state, intent or "start_discussion"
                ):
                    yield sse_data
            else:
                logger.debug(
                    f"[CHAT_GENERATOR] CAIA - 그래프 워크플로우 호출 (의도 분석은 그래프 내부에서 처리)"
                )
                async for sse_data in self._handle_general_workflow(state):
                    yield sse_data
        else:
            # 다른 에이전트들은 기존 로직 유지
            from src.agents.services.agent_intent_service import AgentIntentService

            intent_service = AgentIntentService(self.agent_code)

            if intent_service.is_special_intent(intent):
                logger.debug(
                    f"[CHAT_GENERATOR] {self.agent_code} 특수 의도 감지 - 특수 워크플로우 호출"
                )
                async for sse_data in self._handle_special_workflow(state, intent):
                    yield sse_data
            else:
                logger.debug(
                    f"[CHAT_GENERATOR] {self.agent_code} {intent} 의도 - 일반 워크플로우 호출"
                )
                async for sse_data in self._handle_general_workflow(state):
                    yield sse_data

    async def _handle_special_workflow(self, state: CAIAAgentState, intent: str):
        """
        특수 워크플로우를 처리합니다.

        Args:
            state: CAIAAgentState 객체
            intent: 의도 문자열
        """
        if self.agent_code == "caia" and (
            intent == CAIADiscussionIntent.START_DISCUSSION.value
            or intent == "start_discussion"
            or intent == "discussion"
        ):
            # 토론 에이전트 호출 (start_discussion)
            async for sse_data in self._handle_discussion_agent(state):
                yield sse_data
        else:
            # 기본 워크플로우로 폴백
            async for sse_data in self._handle_general_workflow(state):
                yield sse_data

    async def _handle_discussion_agent(self, state: CAIAAgentState):
        """토론 에이전트를 직접 호출하여 각 노드에서 실시간 스트리밍합니다."""
        logger.debug("[CHAT_GENERATOR] _handle_discussion_agent 호출됨")
        try:
            from src.agents.discussion_agent import DiscussionAgent

            # state에 topic과 speakers가 없으면 DB에서 직접 조회 (Redis는 휘발성이므로 DB를 우선)
            if not state.get("topic") or not state.get("speakers"):
                logger.info(
                    f"[CHAT_GENERATOR] state에 topic/speakers가 없어 DB에서 조회 중... (현재 state: topic={state.get('topic')}, speakers={state.get('speakers')})"
                )

                found = False
                # DB에서 직접 조회 (같은 session_id의 chat_messages 테이블에서 가장 최근 토론 설정 찾기)
                try:
                    from src.database.connection import get_db
                    from src.database.services import (
                        chat_channel_service,
                        chat_message_service,
                    )

                    session_id = state.get("session_id")
                    agent_id = state.get("agent_id", 1)
                    user_id = state.get("user_id")

                    if session_id and user_id:
                        logger.info(
                            f"[CHAT_GENERATOR] DB에서 토론 설정 조회 시작: session_id={session_id}, user_id={user_id}"
                        )
                        db = next(get_db())
                        try:
                            # 채널 조회
                            channel = chat_channel_service.get_by_session_id(
                                db, session_id
                            )
                            if channel:
                                logger.debug(
                                    f"[CHAT_GENERATOR] 채널 발견: channel_id={channel.id}"
                                )
                                # 최근 메시지 조회 (최대 100개, created_at 내림차순으로 이미 정렬됨)
                                # 충분히 많은 메시지를 조회하여 토론 설정 메시지를 찾음
                                messages = chat_message_service.get_recent_messages(
                                    db, channel.id, limit=100
                                )
                                logger.debug(
                                    f"[CHAT_GENERATOR] 최근 메시지 {len(messages)}개 조회됨"
                                )

                                # 최신 메시지부터 검색 (이미 created_at 내림차순으로 정렬됨)
                                # message_metadata에 topic과 speakers가 있는 가장 최근 메시지 찾기
                                for i, msg in enumerate(messages):
                                    if hasattr(msg, "message_metadata"):
                                        metadata = msg.message_metadata
                                        if isinstance(metadata, dict):
                                            topic = metadata.get("topic")
                                            speakers = metadata.get("speakers")
                                            logger.debug(
                                                f"[CHAT_GENERATOR] DB 메시지[{i}] (최신순) metadata 확인: topic={topic}, speakers={speakers if speakers else None}"
                                            )
                                            if topic and speakers:
                                                logger.info(
                                                    f"[CHAT_GENERATOR] DB에서 topic과 speakers 발견 (최신 메시지): topic={topic}, speakers={len(speakers)}명"
                                                )
                                                state["topic"] = topic
                                                state["speakers"] = speakers
                                                if "discussion_rules" in metadata:
                                                    state["discussion_rules"] = (
                                                        metadata.get(
                                                            "discussion_rules", []
                                                        )
                                                    )
                                                if "tools" in metadata:
                                                    state["tools"] = metadata.get(
                                                        "tools"
                                                    )
                                                found = True
                                                break
                            else:
                                logger.warning(
                                    f"[CHAT_GENERATOR] 채널을 찾을 수 없음: session_id={session_id}"
                                )
                        finally:
                            db.close()
                    else:
                        logger.warning(
                            f"[CHAT_GENERATOR] session_id 또는 user_id가 없음: session_id={session_id}, user_id={user_id}"
                        )
                except Exception as e:
                    logger.error(
                        f"[CHAT_GENERATOR] DB에서 topic/speakers 조회 중 오류: {e}",
                        exc_info=True,
                    )

                if not found:
                    logger.warning(
                        "[CHAT_GENERATOR] 이전 대화 이력에서 topic과 speakers를 찾을 수 없습니다."
                    )

            # 토론 에이전트 생성
            discussion_agent = DiscussionAgent()

            # 토론 에이전트의 각 노드를 순차적으로 실행하며 실시간 스트리밍
            logger.debug("[CHAT_GENERATOR] discussion_agent.run_discussion 호출 시작")

            # 토론 실행 및 응답 수집
            discussion_content = ""
            discussion_script = []
            async for sse_data in self._run_discussion_and_collect_content(
                discussion_agent, state
            ):
                yield sse_data
                # SSE 데이터에서 토론 내용 추출
                if "data:" in sse_data and '"token"' in sse_data:
                    try:
                        import json

                        data_part = sse_data.split("data: ")[1].strip()
                        if data_part:
                            parsed_data = json.loads(data_part)
                            if "token" in parsed_data:
                                discussion_content += parsed_data["token"]
                    except:
                        pass  # 파싱 실패 시 무시

            # 토론 완료 후 스크립트를 상태에 저장
            discussion_script = state.get("script", [])
            if discussion_script and isinstance(discussion_script, list):
                logger.info(
                    f"[CHAT_GENERATOR] 토론 완료: state에서 {len(discussion_script)}개 발언을 가져왔습니다"
                )
            else:
                logger.warning(
                    f"[CHAT_GENERATOR] 토론 완료: state에 script가 없거나 잘못된 형식입니다: {type(discussion_script)}"
                )
                discussion_script = []

            # 토론 스크립트를 상태에 저장
            state["script"] = discussion_script
            logger.info(
                f"[CHAT_GENERATOR] 토론 스크립트를 state에 저장했습니다: {len(discussion_script)}개 발언"
            )

            # 토론 완료 후 후처리
            await self._handle_discussion_post_processing(state, discussion_content)

        except asyncio.CancelledError as e:
            logger.warning(
                f"[CHAT_GENERATOR] 토론 에이전트 실행이 취소되었습니다. - {str(e)}"
            )
            logger.warning(
                f"[CHAT_GENERATOR] CancelledError 상세 정보: {type(e).__name__}"
            )
            import traceback

            logger.warning(f"[CHAT_GENERATOR] 스택 트레이스: {traceback.format_exc()}")
            # CancelledError는 정상적인 취소이므로 에러 응답 대신 완료 응답
            yield await self._create_completion_response()
            return
        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 토론 에이전트 호출 실패: {e}")
            yield await self._create_error_response(e)

    async def _run_discussion_and_collect_content(self, discussion_agent, state):
        """토론을 실행합니다."""
        try:
            # 토론 실행에 타임아웃 설정 (설정에서 가져오기)
            from src.utils.config_utils import ConfigUtils

            async with asyncio.timeout(ConfigUtils.get_chat_timeout()):
                async for sse_data in discussion_agent.run_discussion(state):
                    yield sse_data
        except asyncio.TimeoutError:
            logger.warning("[CHAT_GENERATOR] 토론 실행 타임아웃 발생")
            yield await self._create_error_response("토론 실행이 시간 초과되었습니다.")
        except asyncio.CancelledError as e:
            logger.warning(
                f"[CHAT_GENERATOR] _run_discussion_and_collect_content에서 CancelledError 발생: {e}"
            )
            # 취소된 경우 완료 응답으로 처리하여 클라이언트에게 정상 종료 알림
            yield await self._create_completion_response()
        except Exception as e:
            logger.error(
                f"[CHAT_GENERATOR] _run_discussion_and_collect_content에서 오류 발생: {e}"
            )
            yield await self._create_error_response(e)

    async def _handle_discussion_post_processing(self, state, discussion_content):
        """토론 완료 후 후처리를 수행합니다."""
        # 토론 스크립트는 State에 이미 저장되어 있음
        # 워크플로우 후처리 노드들을 직접 호출하여 DB 저장 및 동기화 수행
        try:
            from src.agents.nodes.caia.caia_stm_message_node import CAIASTMMessageNode
            from src.agents.nodes.caia.caia_chat_message_node import CAIAChatMessageNode
            from src.agents.nodes.caia.caia_lgenie_sync_node import CAIALGenieSyncNode
            from src.agents.nodes.caia.caia_memory_node import CAIAMemoryNode
            from src.memory.memory_manager import memory_manager

            # State에 필요한 정보가 있는지 확인
            if not state.get("channel_id"):
                logger.warning("[CHAT_GENERATOR] channel_id가 없어 후처리를 건너뜁니다")
                return

            # 1. STM 메시지 저장
            logger.debug("[CHAT_GENERATOR] 토론 후처리: STM 메시지 저장")

            # STM 저장 전에 script 확인 및 로깅
            script = state.get("script")
            if script and isinstance(script, list) and len(script) > 0:
                logger.info(
                    f"[CHAT_GENERATOR] 토론 후처리: STM 저장 전 state에 {len(script)}개 발언이 있습니다"
                )
            else:
                logger.warning(
                    f"[CHAT_GENERATOR] 토론 후처리: STM 저장 전 state에 script가 없거나 비어있습니다. script={script}, type={type(script)}"
                )

            stm_node = CAIASTMMessageNode(
                memory_manager=memory_manager,
                logger=logger,
                get_agent_id=lambda state: state.get("agent_id", 1),
            )

            try:
                result = await stm_node.save_stm_message(state)
                logger.info(
                    f"[CHAT_GENERATOR] 토론 후처리: STM 메시지 저장 완료. result={result}"
                )
            except Exception as e:
                logger.error(
                    f"[CHAT_GENERATOR] 토론 후처리: STM 메시지 저장 중 오류 발생: {e}",
                    exc_info=True,
                )

            # 2. DB에 채팅 메시지 저장
            logger.debug("[CHAT_GENERATOR] 토론 후처리: 채팅 메시지 저장")
            script = state.get("script")
            if script:
                logger.info(
                    f"[CHAT_GENERATOR] 토론 후처리: state에 {len(script) if isinstance(script, list) else 'N/A'}개 발언이 있습니다"
                )
            else:
                logger.warning(
                    "[CHAT_GENERATOR] 토론 후처리: state에 script가 없습니다"
                )
            chat_message_node = CAIAChatMessageNode(
                logger=logger,
                get_agent_id=lambda state: state.get("agent_id", 1),
            )
            chat_result = await chat_message_node.save_chat_message(state)
            if chat_result:
                state.update(chat_result)
                logger.info(
                    f"[CHAT_GENERATOR] 토론 후처리: 채팅 메시지 저장 완료 - {len(chat_result.get('saved_message_ids', []))}개 메시지 저장됨"
                )
            else:
                logger.warning(
                    "[CHAT_GENERATOR] 토론 후처리: 채팅 메시지 저장 결과가 비어있습니다"
                )

            # 3. LGenie 동기화
            logger.debug("[CHAT_GENERATOR] 토론 후처리: LGenie 동기화")
            lgenie_sync_node = CAIALGenieSyncNode(logger=logger)
            await lgenie_sync_node.sync_lgenie(state)

            # 4. 메모리 추출 및 저장
            logger.debug("[CHAT_GENERATOR] 토론 후처리: 메모리 추출 및 저장")
            memory_node = CAIAMemoryNode(
                memory_manager=memory_manager,
                logger=logger,
                get_agent_id=lambda state: state.get("agent_id", 1),
            )
            await memory_node.extract_and_save_memory_new(state)

            logger.info("[CHAT_GENERATOR] 토론 후처리 완료")

        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 토론 후처리 중 오류: {e}")

    async def _save_stm_message(self, state):
        """STM 메시지를 저장합니다."""
        try:
            from src.agents.nodes.caia.caia_stm_message_node import CAIASTMMessageNode
            from src.memory.memory_manager import memory_manager

            stm_node = CAIASTMMessageNode(
                memory_manager=memory_manager,
                logger=logger,
                get_agent_id=lambda state: state.get("agent_id", 1),
            )
            ### 🫡🫡🫡 summarize!!
            stm_state = {
                "user_id": state.get("user_id"),
                "agent_id": self.agent_id,
                "session_id": state.get("session_id", ""),
                "user_query": state.get("user_query", ""),
                "messages": state.get("messages"),
                "discussion_script": state.get("script", []),  # 토론 스크립트 추가
                "summarize": state.get("summarize", []),
            }

            await stm_node.save_stm_message(stm_state)

        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] STM 메시지 저장 실패: {e}")

    async def _extract_and_save_memory(self, state):
        """메모리를 추출하고 저장합니다."""
        try:
            from src.agents.nodes.caia.caia_memory_node import CAIAMemoryNode
            from src.memory.memory_manager import memory_manager

            memory_node = CAIAMemoryNode(
                memory_manager=memory_manager,
                logger=logger,
                get_agent_id=lambda state: state.get("agent_id", 1),
            )

            memory_state = {
                "user_id": state.get("user_id"),
                "agent_id": self.agent_id,
                "session_id": state.get("session_id") or "",
                "messages": state.get("messages"),
                "actual_user_id": self.actual_user_id,
            }

            await memory_node.extract_and_save_memory(memory_state)

        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 메모리 추출 및 저장 실패: {e}")

    def _get_response_handler(self):
        """에이전트 코드에 맞는 response handler를 레지스트리에서 조회합니다."""
        if self._response_handler is None:
            from src.orchestration.common.agent_interface import orchestration_registry

            # 오케스트레이션 레지스트리에서 response handler 조회
            # app.state에서 레지스트리를 가져오거나 전역 레지스트리 사용
            try:
                # FastAPI app context에서 레지스트리 가져오기 시도
                from fastapi import Request

                # Request 객체가 없으면 전역 레지스트리 사용
                self._response_handler = orchestration_registry.get_response_handler(
                    self.agent_code
                )
            except Exception:
                # 전역 레지스트리 사용
                self._response_handler = orchestration_registry.get_response_handler(
                    self.agent_code
                )

            logger.debug(
                f"[CHAT_GENERATOR] {self.agent_code} 응답 처리기 조회 완료: {type(self._response_handler).__name__}"
            )

        return self._response_handler

    async def _handle_general_workflow(self, state):
        """일반 워크플로우를 처리합니다."""
        try:
            # 오케스트레이터와 워크플로우 확인
            if self.orchestrator is None:
                logger.error("[CHAT_GENERATOR] 오케스트레이터가 None입니다.")
                yield await self._create_error_response(
                    "오케스트레이터가 초기화되지 않았습니다."
                )
                return

            if (
                not hasattr(self.orchestrator, "workflow")
                or self.orchestrator.workflow is None
            ):
                logger.error("[CHAT_GENERATOR] 워크플로우가 초기화되지 않았습니다.")
                yield await self._create_error_response(
                    "워크플로우가 초기화되지 않았습니다."
                )
                return

            # Response handler 조회
            response_handler = self._get_response_handler()

            # 워크플로우 실행 (타임아웃 설정)
            from src.utils.config_utils import ConfigUtils

            try:
                async with asyncio.timeout(ConfigUtils.get_chat_timeout()):
                    # 통합 스트리밍 메서드 사용
                    async for sse_response in self.orchestrator.astream_sse(
                        state, response_handler
                    ):
                        yield sse_response

            except asyncio.TimeoutError:
                logger.warning("[CHAT_GENERATOR] 워크플로우 실행 타임아웃 발생")
                yield await self._create_error_response(
                    "워크플로우 실행이 시간 초과되었습니다."
                )
                return

        except asyncio.CancelledError:
            logger.warning("[CHAT_GENERATOR] 일반 워크플로우 실행이 취소되었습니다.")
            yield await self._create_error_response("워크플로우 실행이 취소되었습니다.")

        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 워크플로우 실행 실패: {e}")
            yield await self._create_error_response(e)

    async def _create_node_output_response(self, node_name: str, node_output: Any):
        """일반 워크플로우 노드 출력을 SSE 응답으로 변환합니다.

        이 메서드는 이제 response handler로 위임합니다.
        하위 호환성을 위해 유지되지만, _handle_general_workflow에서는
        astream_sse를 통해 직접 처리됩니다.
        """
        logger.info(
            f"[CHAT_GENERATOR] node_output received: node={node_name}, output_type={type(node_output)}"
        )
        if isinstance(node_output, dict):
            logger.info(
                f"[CHAT_GENERATOR] node_output keys: {list(node_output.keys())}"
            )

        # Response handler를 통해 처리
        response_handler = self._get_response_handler()
        async for response in response_handler.handle_response(node_name, node_output):
            yield response

    async def _stream_final_answer(self, final_output):
        """최종 답변을 스트리밍합니다.

        이 메서드는 하위 호환성을 위해 유지되지만,
        새로운 코드에서는 response handler를 사용하는 것을 권장합니다.
        """

        content = ""
        if isinstance(final_output, dict):
            messages = final_output.get("messages", [])
            topic_suggestions = final_output.get("topic_suggestions")

            # 먼저 messages에서 content 추출
            if messages and len(messages) > 0:
                last_message = messages[-1]
                # AIMessage 객체에서 content 추출
                if hasattr(last_message, "content"):
                    content = last_message.content
                else:
                    content = str(last_message)
            else:
                # messages가 없는 경우 다른 키 확인
                content = final_output.get("content", str(final_output))

            # topic_suggestions가 있으면 추가 (discussable_topic_node에서 이미 포맷팅된 경우는 제외)
            if topic_suggestions and content and "### 추천 토론 주제" not in content:
                content += "\n\n"
                content += "### 추천 토론 주제\n"
                for i, topic in enumerate(topic_suggestions, 1):
                    content += f"{i}. {topic}\n"
        else:
            # 단순 문자열인 경우
            content = str(final_output)

        if content:
            # sse_metadata가 있으면 우선 처리
            if isinstance(final_output, dict) and "sse_metadata" in final_output:
                sse_metadata = final_output["sse_metadata"]
                streaming = sse_metadata.get("streaming", True)

                if streaming:
                    # 문자 단위 스트리밍
                    for char in content:
                        yield await SSEResponse.create_llm(
                            token=char, done=False
                        ).send()
                        await asyncio.sleep(0.01)

            # DB 저장은 워크플로우에서 처리하므로 여기서는 스트리밍만 수행
            # 내용을 토큰 단위로 스트리밍 (sse_metadata가 없거나 streaming이 True인 경우)
            if not (isinstance(final_output, dict) and "sse_metadata" in final_output):
                for char in content:
                    yield await SSEResponse.create_llm(token=char, done=False).send()
                    await asyncio.sleep(0.01)  # 스트리밍 효과

            # 최종 완료 응답
            event_data = {}
            if isinstance(final_output, dict):
                if "topic_suggestions" in final_output:
                    event_data["topic_suggestions"] = final_output["topic_suggestions"]
                if "sse_metadata" in final_output:
                    sse_metadata = final_output["sse_metadata"]
                    if "event_data" in sse_metadata:
                        event_data.update(sse_metadata["event_data"])

            yield await SSEResponse.create_llm(
                token=content,
                done=True,
                message_res=MessageResponse.from_parameters(
                    content=content,
                    role="assistant",
                    images=(
                        final_output.get("images", [])
                        if isinstance(final_output, dict)
                        else []
                    ),
                    links=(
                        final_output.get("links", [])
                        if isinstance(final_output, dict)
                        else []
                    ),
                    event_data=event_data if event_data else None,
                ),
            ).send()
        else:
            # 내용이 없는 경우
            error_content = "죄송합니다. 응답을 생성할 수 없습니다."
            for char in error_content:
                yield await SSEResponse.create_llm(token=char, done=False).send()
                await asyncio.sleep(0.01)

            yield await SSEResponse.create_llm(
                token=error_content,  # 전체 에러 내용을 token에 포함
                done=True,
                message_res=MessageResponse.from_parameters(
                    content=error_content,
                    role="assistant",
                    links=[],
                    images=[],
                ),
            ).send()

    async def _create_memory_completion_response(self):
        """메모리 완료 응답을 생성합니다."""
        return await SSEResponse.create_status(
            status=AgentStatus.INTENT_ANALYSIS_COMPLETE
        ).send()

    async def _process_search_agent_tools(self, search_output):
        """검색 에이전트 도구 출력을 처리합니다."""
        return await SSEResponse.create_status(
            status=AgentStatus.INTENT_ANALYSIS_COMPLETE
        ).send()

    async def _stream_search_agent_answer(self, node_output):
        return await SSEResponse.create_llm(
            token=node_output["messages"][0].content,
            done=True,
        ).send()

    async def _create_error_response(self, error: Exception):
        """오류 응답을 생성합니다."""
        logger.error(f"[CHAT_ROUTER] 오류 발생: {error}")
        return await SSEResponse.create_error(
            error_message=f"처리 중 오류가 발생했습니다: {str(error)}"
        ).send()

    async def _create_completion_response(self):
        """완료 응답을 생성합니다."""
        # chat_id는 session_id를 사용
        chat_id = getattr(self, "session_id", "")
        # message_id는 타임스탬프 기반으로 생성
        message_id = f"msg_{self.start_time}" if self.start_time else ""

        # 디버그 정보 수집
        # collector = getattr(self, "debug_collector", None) # ⚠️ 동작 안함! (항상 None)

        # if collector is None:
        #     # DebugInfoCollector가 없는 경우 빈 리스트 반환
        #     debug_info = []
        # else:
        #     debug_info = collector.get_logs()

        from src.utils.log_collector import collector

        debug_info = collector.get_logs()

        return await SSEResponse.create_close(
            chat_id=chat_id or "",
            message_id=message_id or "",
            chat_session_id="",  # 더 이상 사용하지 않음
            debug_info=debug_info,
        ).send()

    async def _handle_stream_continuity(
        self, session_id: str, user_id: str, client_id: str | None = None
    ):
        """스트림 연속성 처리"""
        try:
            # 기존 스트림 상태 확인
            existing_stream = stream_manager.get_stream(session_id)

            if existing_stream and existing_stream.is_active:
                logger.debug(f"[CHAT_GENERATOR] 기존 스트림 발견: {session_id}")

                # 클라이언트 연결 추가
                if client_id:
                    stream_manager.add_client_to_stream(session_id, client_id)

                # 기존 스트림이 진행 중인지 확인
                if existing_stream.stream_generator:
                    logger.debug(f"[CHAT_GENERATOR] 기존 스트림 재연결: {session_id}")
                    # 기존 스트림의 상태를 현재 인스턴스에 복사
                    if existing_stream.current_state:
                        # 기존 상태에서 이어서 처리
                        await self._resume_from_existing_state(existing_stream)
                        return

            # 새 스트림 생성 또는 기존 스트림이 없는 경우
            # actual_user_id가 설정되지 않은 경우 기본값 사용
            actual_user_id = getattr(self, "actual_user_id", None) or user_id
            stream_state = stream_manager.create_stream(
                session_id, self.agent_code, actual_user_id
            )
            if client_id:
                stream_manager.add_client_to_stream(session_id, client_id)

            logger.debug(f"[CHAT_GENERATOR] 새 스트림 시작: {session_id}")

        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 스트림 연속성 처리 실패: {e}")

    async def _resume_from_existing_state(self, stream_state):
        """기존 상태에서 스트림 재개"""
        try:
            logger.debug(
                f"[CHAT_GENERATOR] 기존 상태에서 재개: {stream_state.current_node}"
            )

            # 기존 스트림 제너레이터가 있으면 재사용
            if stream_state.stream_generator:
                async for chunk in stream_state.stream_generator:
                    yield chunk
                return

        except Exception as e:
            logger.error(f"[CHAT_GENERATOR] 기존 상태 재개 실패: {e}")

    async def _update_stream_state(
        self, current_node: str = None, current_state: Dict[str, Any] = None
    ):
        """스트림 상태 업데이트"""
        if self.session_id:
            stream_manager.update_stream_state(
                self.session_id, current_node, current_state
            )

    async def _set_stream_generator(self, generator):
        """스트림 제너레이터 설정"""
        if self.session_id:
            stream_manager.set_stream_generator(self.session_id, generator)
