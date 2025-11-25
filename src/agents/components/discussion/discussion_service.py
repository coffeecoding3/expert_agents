import asyncio
from datetime import datetime
from logging import getLogger
from typing import Any, Dict, List, Optional

from src.agents.components.search_agent.web_search import WebSearch

from configs.app_config import load_config  # 설정 로더 임포트
from src.agents.components.common.llm_component import LLMComponent
from src.utils.config_utils import ConfigUtils
from src.agents.components.common.llm_response_json_parser import LLMResponseJsonParser
from src.agents.components.discussion.discussion_proceed_component import (
    DiscussionProceedComponent,
)
from src.agents.search_agent import SearchAgentWrapper
from src.capabilities.servers.external.mcp_client import MCPClient
from src.llm.interfaces import ChatMessage
from src.llm.interfaces.chat import MessageRole
from src.llm.manager import llm_manager
from src.prompts.prompt_manager import prompt_manager
from src.utils.log_collector import collector

from pydantic import BaseModel, Field, conlist
from langchain_core.messages import AIMessage

logger = getLogger("agents.discussion")


class Message(BaseModel):
    """
    Wow Point 응답 형식 정의
    """

    message: str = Field(..., description="메인 메시지")
    topic_suggestions: conlist(str, min_length=2, max_length=2) = Field(
        ..., description="추가 질문"
    )


class Discussion:

    DISCUSSION_MAX_TURN = 8
    DISCUSSION_MIN_TURN = 5

    def __init__(self):
        # LLM 매니저를 통해 설정을 가져옴
        self.config = load_config()
        self.provider = None  # LLM 매니저에서 기본값 사용
        self.model = None  # LLM 매니저에서 기본값 사용
        # DiscussionProceedComponent 사용
        self.proceed_component = DiscussionProceedComponent()

    # 1. 토론 주제 및 참여자 선정
    async def setup_discussion(self, query, chat_history, state=None) -> dict:
        fallback_response = {"topic": None, "speakers": []}

        try:
            rendered = prompt_manager.render_template(
                "discussion/setup_discussion_v2.j2",
                {
                    "query": query,
                    "chat_history": chat_history,
                    "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            messages = [ChatMessage(role=MessageRole.USER, content=rendered)]

            response = await llm_manager.chat(
                messages=messages,
                temperature=0.1,
            )

            # Provider에서 제공하는 response_time과 usage 사용
            response_time = response.response_time or 0.0
            token_count = 0

            # Token 사용량 추적 (state가 있는 경우)
            if state and "total_tokens" in state and response.usage:
                usage = response.usage
                input_tokens = usage.get("input_tokens") or usage.get(
                    "prompt_tokens", 0
                )
                output_tokens = usage.get("output_tokens") or usage.get(
                    "completion_tokens", 0
                )
                total_tokens = usage.get("total_tokens", 0)

                state["total_tokens"]["input_tokens"] += input_tokens
                state["total_tokens"]["output_tokens"] += output_tokens
                state["total_tokens"]["total_tokens"] += total_tokens
                token_count = total_tokens
            elif response.usage:
                # state가 없어도 response에서 직접 가져오기
                usage = response.usage
                token_count = usage.get("total_tokens", 0)

            json_parser = LLMResponseJsonParser(fallback_response=fallback_response)

            parsed_data = json_parser.parse(response.content)

            # provider에서 제공하는 token_count와 response_second 추가
            parsed_data["token_count"] = token_count
            parsed_data["response_second"] = response_time

            return parsed_data

        except Exception as e:
            logger.warning(f"[DISCUSSION] setup discussion failed: {e}")

            # ⚠️ 걍 에러 발생시켜야되나?
            fallback_response["token_count"] = 0
            fallback_response["response_second"] = 0.0
            return fallback_response

    # 2. 참여자별 참고 자료 검색 (병렬처리)
    async def get_discussion_materials(self, topic, speakers, state=None, tools=None):
        import time

        # 전체 자료 수집 시간 측정 시작
        total_start_time = time.time()
        total_token_count = 0

        # 사내지식 검색 함수 - MCP 클라이언트 사용
        async def _internal_search(query: str, state=None):
            try:
                # state에서 사용자 정보 추출 (DiscussionState에서 user_id를 sso_id로 변환)
                sso_id = None
                if state and isinstance(state, dict):
                    user_id = state.get("user_id")

                    if user_id:
                        # user_id(숫자)를 sso_id(문자열)로 변환
                        from src.apps.api.user.user_service import user_auth_service

                        sso_id = user_auth_service.get_sso_id_from_user_id(user_id)
                    else:
                        logger.warning(f"[DISCUSSION] state에 user_id가 없습니다.")
                else:
                    logger.warning(f"[DISCUSSION] state가 dict가 아님: {type(state)}")

                # 통일된 MCP 서비스 사용
                from src.capabilities.mcp_service import mcp_service
                from src.utils.config_utils import ConfigUtils

                # MCP 도구 실행 (스키마 검증 포함)
                # TODO: default_system_codes 추가 필요(엘지니 지식창고)
                default_system_codes = ConfigUtils.get_default_system_codes()
                # caia_system_codes = ConfigUtils.get_caia_system_codes()
                # 두 리스트를 합치고 중복 제거
                # system_codes = list(set(default_system_codes + caia_system_codes))
                result = await asyncio.wait_for(
                    mcp_service.call_mcp_tool_with_validation(
                        tool_name="retrieve_coporate_knowledge",  # 내부 도구 이름 사용
                        client_name="lgenie",
                        args={
                            "query": query,
                            "system_codes": default_system_codes,
                            "top_k": 5,
                        },
                        sso_id=sso_id,
                    ),
                    timeout=ConfigUtils.get_lgenie_timeout(),  # 설정에서 타임아웃 가져오기
                )
                # 결과 처리 - MCPHandler 응답 형식에 맞게 처리
                if result and isinstance(result, dict):
                    # MCPHandler의 execute_tool 결과에서 실제 데이터 추출
                    actual_result = result.get("result", [])

                    if result.get("is_error"):
                        logger.warning(
                            f"[DISCUSSION] MCP 도구 오류: {result.get('error_message', '알 수 없는 오류')}"
                        )
                        return [
                            f"`{query}`에 대한 사내 자료 검색 중 오류가 발생했습니다."
                        ]

                    # MCP 결과가 {'documents': [...]} 형태인 경우 처리
                    if isinstance(actual_result, dict) and "documents" in actual_result:
                        documents = actual_result.get("documents", [])
                        if documents and isinstance(documents, list):
                            processed_results = []
                            for item in documents:
                                if isinstance(item, dict):
                                    # Document 모델의 필드들을 활용하여 출처 정보 포함
                                    processed_item = {
                                        "content": item.get(
                                            "context", item.get("content", "")
                                        ),
                                        "title": item.get("title", ""),
                                        "filename": item.get("filename", ""),
                                        "view_url": item.get("view_url", ""),
                                        "score": item.get("score", 0.0),
                                        "reg_date": item.get("reg_date", ""),
                                        "custom_title": item.get("custom_title", ""),
                                    }
                                    processed_results.append(processed_item)
                                else:
                                    processed_results.append(item)
                            return processed_results
                        else:
                            logger.warning(
                                f"[DISCUSSION] MCP 서버에서 빈 documents 반환"
                            )
                            return [f"`{query}`에 대한 사내 자료를 찾을 수 없습니다."]
                    elif actual_result and isinstance(actual_result, list):
                        # 기존 리스트 형태 결과 처리
                        processed_results = []
                        for item in actual_result:
                            if isinstance(item, dict):
                                # Document 모델의 필드들을 활용하여 출처 정보 포함
                                processed_item = {
                                    "content": item.get(
                                        "context", item.get("content", "")
                                    ),
                                    "filename": item.get("filename", ""),
                                }
                                processed_results.append(processed_item)
                            else:
                                processed_results.append(item)
                        return processed_results
                    else:
                        logger.warning(
                            f"[DISCUSSION] MCP 서버에서 빈 결과 반환 - actual_result: {actual_result}"
                        )
                        return [f"`{query}`에 대한 사내 자료를 찾을 수 없습니다."]
                else:
                    logger.warning(
                        f"[DISCUSSION] MCP 서버에서 예상치 못한 응답 형식: {type(result)}"
                    )
                    return [f"`{query}`에 대한 사내 자료를 찾을 수 없습니다."]

            except asyncio.TimeoutError:
                logger.warning(f"[DISCUSSION] 사내지식 검색 타임아웃: {query}")
                return [f"`{query}`에 대한 사내 자료 검색이 시간 초과되었습니다."]
            except asyncio.CancelledError:
                logger.warning(f"[DISCUSSION] 사내지식 검색 취소됨: {query}")
                return [f"`{query}`에 대한 사내 자료 검색이 취소되었습니다."]
            except Exception as e:
                logger.warning(f"[DISCUSSION] 사내지식 검색 실패: {e}")
                return [f"`{query}`에 대한 사내 자료 검색 중 오류가 발생했습니다."]

        # 웹 검색 함수 (Gemini Web Search Tool 사용)
        async def _web_search(query: str) -> List[Dict[str, Any]]:
            logger.info(f"[DISCUSSION] 웹 검색 시작: query='{query}'")
            try:
                from src.agents.tools.common.gemini_web_search_tool import (
                    GeminiWebSearchTool,
                )

                tool = GeminiWebSearchTool()
                tool_result = await asyncio.wait_for(
                    tool.run({"query": query}),
                    timeout=ConfigUtils.get_chat_timeout(),
                )

                if not tool_result.get("success", False):
                    error_msg = tool_result.get("error", "알 수 없는 오류")
                    logger.error(f"[DISCUSSION] 웹 검색 실패: {error_msg}")
                    return GeminiWebSearchTool.create_error_result(error_msg)

                response = tool_result.get("response", {})

                # 결과 형식 변환 (gemini_web_search_tool에서 관리)
                result = GeminiWebSearchTool.format_result_as_list(response)

                # 로깅
                if result and isinstance(result[0], dict):
                    summary = result[0].get("summary", "")
                    references = result[0].get("reference", [])
                    search_queries = result[0].get("search_queries", [])
                    logger.info(
                        f"[DISCUSSION] 웹 검색 완료: summary 길이={len(summary)}자, "
                        f"reference={len(references)}개, search_queries={len(search_queries)}개"
                    )

                return result
            except asyncio.TimeoutError:
                logger.warning(
                    f"[DISCUSSION] 웹 검색 타임아웃: query='{query}', timeout={ConfigUtils.get_chat_timeout()}초"
                )
                return GeminiWebSearchTool.create_error_result(
                    f"`{query}`에 대한 웹 검색이 시간 초과되었습니다."
                )
            except asyncio.CancelledError:
                logger.warning(f"[DISCUSSION] 웹 검색 취소됨: query='{query}'")
                return GeminiWebSearchTool.create_error_result(
                    f"`{query}`에 대한 웹 검색이 취소되었습니다."
                )
            except Exception as e:
                logger.error(
                    f"[DISCUSSION] 웹 검색 실패: query='{query}', 오류: {e}",
                    exc_info=True,
                )
                return GeminiWebSearchTool.create_error_result(
                    f"`{query}`에 대한 웹 검색 중 오류가 발생했습니다: {str(e)}"
                )

        # 토론 전용 임시 LLM Search 함수
        async def _external_search(query: str) -> str:
            try:
                llm_component = LLMComponent(agent_code="caia")

                response = await asyncio.wait_for(
                    llm_component.chat_with_prompt(
                        prompt_template="discussion/discussion_llm_search.j2",
                        template_vars={"query": query},
                        temperature=0.1,
                    ),
                    timeout=ConfigUtils.get_chat_timeout(),  # 설정에서 타임아웃 가져오기
                )

                # Provider에서 제공하는 response_time과 usage 사용
                # Token 추적
                token_count = 0
                if response.usage:
                    usage = response.usage
                    token_count = usage.get("total_tokens", 0)
                    # 전체 token에 누적
                    nonlocal total_token_count
                    total_token_count += token_count

                response_content = response.content
                return [response_content]
            except asyncio.TimeoutError:
                logger.warning(f"외부 검색 LLM 호출 타임아웃: {query}")
                return ["검색 결과를 가져올 수 없습니다."]
            except asyncio.CancelledError:
                logger.warning(f"외부 검색 LLM 호출 취소됨: {query}")
                return ["검색이 취소되었습니다."]
            except Exception as e:
                logger.error(f"외부 검색 LLM 호출 오류: {e}")
                return ["검색 중 오류가 발생했습니다."]

        # 각 전문가별 자료 수집을 병렬로 처리하는 함수
        async def _collect_speaker_materials(speaker, state=None, enabled_tools=None):
            speaker_name = speaker.get("speaker", "")
            tmp = {"speaker": speaker_name, "materials": []}

            internal_search_query = speaker.get("internal_search_query", "")
            llm_search_query = speaker.get("llm_search_query", "")
            web_search_query = speaker.get("web_search_query", "")

            # 도구가 지정되지 않았으면 모든 도구 활성화 (기본값)
            if enabled_tools is None or len(enabled_tools) == 0:
                enabled_tools = [
                    "gemini_web_search",
                    "llm_knowledge",
                    "internal_knowledge",
                ]

            # 내부/외부/웹 검색을 병렬로 실행 (활성화된 도구만)
            tasks = []

            # internal_knowledge 검색
            if "internal_knowledge" in enabled_tools and internal_search_query:
                tasks.append(_internal_search(internal_search_query, state))
            else:
                tasks.append(asyncio.create_task(asyncio.sleep(0, result=[])))

            # llm_knowledge 검색
            if "llm_knowledge" in enabled_tools and llm_search_query:
                tasks.append(_external_search(llm_search_query))
            else:
                tasks.append(asyncio.create_task(asyncio.sleep(0, result=[])))

            # gemini_web_search 검색 (web_search_query 사용)
            if "gemini_web_search" in enabled_tools and web_search_query:
                tasks.append(_web_search(web_search_query))
            else:
                tasks.append(asyncio.create_task(asyncio.sleep(0, result=[])))

            # 병렬로 검색 실행 (취소 방지)
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=ConfigUtils.get_chat_timeout(),
                )  # 설정에서 타임아웃 가져오기
                # 예외가 발생한 경우 빈 결과로 처리
                internal_results = (
                    results[0] if not isinstance(results[0], Exception) else []
                )
                external_results = (
                    results[1] if not isinstance(results[1], Exception) else []
                )
                web_results = (
                    results[2] if not isinstance(results[2], Exception) else []
                )
            except asyncio.TimeoutError:
                logger.warning("검색 타임아웃 발생, 빈 결과로 처리")
                internal_results, external_results, web_results = [], [], []
            except asyncio.CancelledError:
                logger.warning("검색이 취소됨, 빈 결과로 처리")
                internal_results, external_results, web_results = [], [], []
            except Exception as e:
                logger.error(f"검색 중 오류: {e}, 빈 결과로 처리")
                internal_results, external_results, web_results = [], [], []

            tmp["materials"].append(
                {
                    "internal_search_query": internal_search_query,
                    "internal_results": internal_results,
                }
            )
            tmp["materials"].append(
                {
                    "llm_search_query": llm_search_query,
                    "external_results": external_results,
                }
            )
            tmp["materials"].append(
                {
                    "web_query": web_search_query,
                    "web_results": web_results,
                }
            )

            return tmp

        # 모든 전문가의 자료 수집을 병렬로 실행 (취소 방지)
        materials_tasks = [
            _collect_speaker_materials(speaker, state, tools) for speaker in speakers
        ]

        # 각 태스크를 개별적으로 처리하여 하나의 실패가 전체를 취소하지 않도록 함
        materials = []
        for task in materials_tasks:
            try:
                result = await asyncio.wait_for(
                    task, timeout=ConfigUtils.get_chat_timeout()
                )  # 설정에서 타임아웃 가져오기
                materials.append(result)
            except asyncio.TimeoutError:
                logger.warning("자료 수집 타임아웃 발생, 빈 결과로 처리")
                materials.append({"speaker": "unknown", "materials": []})
            except asyncio.CancelledError:
                logger.warning("자료 수집이 취소됨, 빈 결과로 처리")
                materials.append({"speaker": "unknown", "materials": []})
            except Exception as e:
                logger.error(f"자료 수집 중 오류: {e}, 빈 결과로 처리")
                materials.append({"speaker": "unknown", "materials": []})

        # 전체 자료 수집 시간 계산
        total_response_time = time.time() - total_start_time

        # materials에 token_count와 response_second 추가 (dict로 반환)
        return {
            "materials": materials,
            "token_count": total_token_count,
            "response_second": total_response_time,
        }

    # 2.5. 발화 생성 (단일 발화) - DiscussionProceedComponent 사용
    async def generate_speech(
        self, topic, speaker, material, script, discussion_rules, state=None
    ):
        """단일 발화를 생성합니다."""
        try:
            return await self.proceed_component.generate_speech(
                topic=topic,
                speaker=speaker,
                material=material,
                script=script,
                discussion_rules=discussion_rules,
                state=state,
            )
        except Exception as e:
            logger.warning(f"[DISCUSSION] speech generation failed: {e}")
            return f"{speaker}의 발언이 생성되지 않았습니다."

    # 3. 토론 진행
    async def proceed_discussion(
        self, topic, speakers, materials, discussion_rules=[], state=None
    ):
        import time

        # 전체 토론 진행 시간 추적 (각 LLM 호출의 response_time을 누적)
        total_start_time = time.time()
        total_token_count = 0

        script = []
        turn_count = 0
        participants = [tmp["speaker"] for tmp in speakers]

        # 발화자 선정 및 토론 종료 판단 함수 (LLM)
        async def manage_discussion_flow():

            fallback_response = {
                "progress": "CONTINUE",
                "next_speaker": participants[0] if participants else "",
            }

            try:
                # script가 비어있으면 빈 리스트로 시작
                # (host 발언은 get_materials 노드에서 이미 스트리밍되었으므로 여기서는 생성하지 않음)
                if script:
                    script_content = script
                else:
                    script_content = []

                rendered = prompt_manager.render_template(
                    "discussion/manage_discussion_flow.j2",
                    {
                        "topic": topic,
                        "participants": participants,
                        "script": script_content,
                        "discussion_rules": discussion_rules,
                    },
                )
                messages = [ChatMessage(role=MessageRole.USER, content=rendered)]

                response = await llm_manager.chat(
                    messages=messages,
                    temperature=0.1,
                )

                # Provider에서 제공하는 response_time과 usage 사용
                response_time = response.response_time or 0.0
                token_count = 0

                # Token 사용량 추적 (state가 있는 경우)
                if state and "total_tokens" in state and response.usage:
                    usage = response.usage
                    input_tokens = usage.get("input_tokens") or usage.get(
                        "prompt_tokens", 0
                    )
                    output_tokens = usage.get("output_tokens") or usage.get(
                        "completion_tokens", 0
                    )
                    total_tokens = usage.get("total_tokens", 0)

                    state["total_tokens"]["input_tokens"] += input_tokens
                    state["total_tokens"]["output_tokens"] += output_tokens
                    state["total_tokens"]["total_tokens"] += total_tokens
                    token_count = total_tokens
                elif response.usage:
                    # state가 없어도 response에서 직접 가져오기
                    usage = response.usage
                    token_count = usage.get("total_tokens", 0)

                json_parser = LLMResponseJsonParser(fallback_response=fallback_response)

                parsed_data = json_parser.parse(response.content)

                # provider에서 제공하는 token_count와 response_second 추가
                parsed_data["token_count"] = token_count
                parsed_data["response_second"] = response_time

                return parsed_data

            except Exception as e:
                logger.warning(f"[DISCUSSION] 3.1 discussion_flow failed: {e}")

                # ⚠️ 걍 에러 발생시켜야되나?
                fallback_response["token_count"] = 0
                fallback_response["response_second"] = 0.0
                return fallback_response

        # 발화 최대 턴수 안에서 토론 진행
        while turn_count < Discussion.DISCUSSION_MAX_TURN:
            turn_count += 1

            # 발화자 선정 및 토론 종료 판단
            next_flow = await manage_discussion_flow()
            # next_flow: {"progress": "CONTINUE", "next_speaker": "Alice"}
            # next_flow: {"progress": "END", "next_speaker": ""}
            # manage_discussion_flow의 token과 시간 누적
            if isinstance(next_flow, dict):
                flow_token_count = next_flow.get("token_count", 0)
                total_token_count += flow_token_count
            collector.log_append("discussion_flow", next_flow)

            # 발화 최소 턴수 진행
            if turn_count <= Discussion.DISCUSSION_MIN_TURN:
                if next_flow["progress"] == "END":
                    next_flow["progress"] = "CONTINUE"

            # 발화자 없을 때 예외처리
            if next_flow["progress"] == "CONTINUE":
                if not next_flow["next_speaker"]:
                    next_flow["next_speaker"] = participants[
                        (turn_count - 1) % len(participants)
                    ]  # ⚠️ 발화자가 직전발화자랑 같아질 가능성 있음..

            # 발화자 선정 스트리밍
            if next_flow["progress"] == "CONTINUE":
                speaker = next_flow["next_speaker"]
                yield {
                    "type": "speaker_selected",
                    "data": {
                        "speaker": speaker,
                        "turn": turn_count,
                        "message": f"{speaker}이(가) 발언할 차례입니다.",
                    },
                }

                # 발화 생성
                # materials = [{"speaker": str  "materials": List[str]}, ...]
                material = [
                    m["materials"] for m in materials if m["speaker"] == speaker
                ]  # ⚠️ 이런거때문에 schema기반 validate가 필요할듯

                # material이 비어있으면 빈 리스트로 처리
                if not material:
                    material = []

                # 발화 시작 스트리밍
                yield {
                    "type": "speech_start",
                    "data": {
                        "speaker": speaker,
                        "next_speaker": speaker,  # 발화 시작 시점에는 현재 발화자가 next_speaker
                        "message": f"{speaker}이(가) 발언을 시작합니다...",
                    },
                }

                # 발화 생성 (단순화)
                speech_result = await self.generate_speech(
                    topic, speaker, material, script, discussion_rules, state
                )

                # generate_speech가 dict를 반환하므로 처리
                if isinstance(speech_result, dict):
                    accumulated_speech = speech_result.get("content", "")
                    # token과 시간 누적
                    total_token_count += speech_result.get("token_count", 0)
                else:
                    # 기존 호환성을 위해 문자열도 처리
                    accumulated_speech = speech_result

                yield {
                    "type": "speech_content",
                    "data": {
                        "speaker": speaker,
                        "message": f"{speaker}가 말하는 중...",
                        "content": accumulated_speech,
                    },
                }

                # 최종 발화 데이터 생성 - accumulated_speech가 있으면 script에 추가
                if accumulated_speech and accumulated_speech.strip():
                    next_speech = {
                        "speaker": speaker,
                        "speech": accumulated_speech.strip(),
                    }
                    collector.log_append("discussion_script", next_speech)
                    script.append(next_speech)

                    # 발화 완료 이벤트 - script에만 추가하고 SSE로 전송하지 않음 (중복 방지)
                    # yield {"type": "speech_complete", "data": next_speech}

            # 토론 종료
            elif next_flow["progress"] == "END":
                yield {
                    "type": "discussion_ending",
                    "data": {
                        "message": "토론이 종료되었습니다.",
                        "total_turns": turn_count,
                    },
                }
                break

            # exception
            else:
                break

        # 전체 토론 진행 시간 계산
        total_response_time = time.time() - total_start_time

        # manage_discussion_flow에서 나온 token도 누적 (이미 state에 추가되었지만, 전체 합계를 위해)
        # 제너레이터에서는 return 대신 yield를 사용
        # 최종 script 결과를 yield (전체 token과 시간 포함)
        yield {
            "type": "final_script",
            "data": {
                "script": script,
                "token_count": total_token_count,
                "response_second": total_response_time,
            },
        }

    # 4. 토론 요약, WOW Point 도출
    async def wrap_up_discussion(self, topic, script, state=None):
        fallback_response = ""

        try:
            import time

            rendered = prompt_manager.render_template(
                "discussion/wrap_up_discussion_v2.j2",
                {
                    "topic": topic,
                    "script": script,
                },
            )
            messages = [ChatMessage(role=MessageRole.USER, content=rendered)]

            response = await llm_manager.chat(
                messages=messages,
                temperature=0.1,
            )

            # Provider에서 제공하는 response_time과 usage 사용
            response_time = response.response_time or 0.0
            token_count = 0

            content = getattr(response, "content", str(response))

            schema = Message.model_json_schema()
            fallback_response = {"message": "", "topic_suggestions": []}
            json_parser = LLMResponseJsonParser(
                fallback_response=fallback_response, schema=schema
            )
            parsed = json_parser.parse(content)

            # Token 사용량 추적 (state가 있는 경우)
            if state and "total_tokens" in state and response.usage:
                usage = response.usage
                input_tokens = usage.get("input_tokens") or usage.get(
                    "prompt_tokens", 0
                )
                output_tokens = usage.get("output_tokens") or usage.get(
                    "completion_tokens", 0
                )
                total_tokens = usage.get("total_tokens", 0)

                state["total_tokens"]["input_tokens"] += input_tokens
                state["total_tokens"]["output_tokens"] += output_tokens
                state["total_tokens"]["total_tokens"] += total_tokens
                token_count = total_tokens
            elif response.usage:
                # state가 없어도 response에서 직접 가져오기
                usage = response.usage
                token_count = usage.get("total_tokens", 0)

            return {
                "message": [AIMessage(content=parsed["message"])],
                "topic_suggestions": parsed["topic_suggestions"],
                "success": True,
                "token_count": token_count,
                "response_second": response_time,
            }

        except Exception as e:
            logger.warning(f"[DISCUSSION] wrap up discussion failed: {e}")
            return {
                "messages": [
                    AIMessage(content="죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                ],
                "topic_suggestions": [],
                "success": False,
                "error": str(e),
                "token_count": 0,
                "response_second": 0.0,
            }
