import asyncio
from typing import Any, Dict

from src.agents.components.discussion.discussion_message_storage import (
    DiscussionMessageStorage,
)
from src.agents.components.discussion.discussion_service import Discussion
from src.agents.components.discussion.discussion_utils import (
    DISCUSSION_CONTEXT,
    DISCUSSION_ROLE_HOST,
)
from src.orchestration.states.discussion_state import DiscussionState
from src.schemas.sse_response import (
    AgentStatus,
    DiscussionStatus,
    SSEResponse,
)
from src.utils.log_collector import collector


class GetDiscussionMaterialsNode:

    def __init__(self, logger):
        self.logger = logger
        self.discussion = Discussion()
        # 메시지 저장 모듈
        self.message_storage = DiscussionMessageStorage(logger_instance=logger)

    async def run(self, state: DiscussionState):
        """자료 수집 노드 - SSE 스트리밍과 상태 반환을 모두 지원"""
        self.logger.info(
            "[DISCUSSION: 2. materials_start] 자료 수집 시작 - RUN 메서드 실행됨"
        )

        topic = state.get("topic", "")
        speakers = state.get("speakers", [])

        if not topic or not speakers:
            self.logger.error(
                "[DISCUSSION: 2. materials_failed] 토론 주제 또는 전문가 정보 없음"
            )
            error_text = (
                "토론 주제 또는 전문가 정보가 없어 자료를 수집할 수 없습니다.\n"
            )
            sse_response = SSEResponse.create_error(
                error_message=error_text,
            )
            yield await sse_response.send()
            return

        # 토론 시작 발언 스트리밍 (setup_node와 동일한 로직)
        if topic and topic.strip() and speakers and len(speakers) > 0:
            host_script = f"오늘 토론 주제는 '{topic}'입니다.\n"
            host_script += f"이번 토론에서는 {', '.join([s.get('speaker', '') for s in speakers])} 이렇게 {len(speakers)}명을 모셨습니다. 토론을 시작하겠습니다.\n"

            for i, char in enumerate(host_script):
                is_done = i == len(host_script) - 1
                sse_response = SSEResponse.create_multi_llm_streaming(
                    token=char,
                    context=DISCUSSION_CONTEXT,
                    llm_role=DISCUSSION_ROLE_HOST,
                    done=is_done,
                    appendable=False,
                )
                yield await sse_response.send()

            # Setup 메시지를 DB에 저장 (SSE 스트리밍 후 비동기로 저장)
            try:
                await self.message_storage.save_host_setup_message(
                    state=state,
                    host_script=host_script,
                )
            except Exception as e:
                self.logger.error(
                    f"[DISCUSSION: 2. materials] Host setup 메시지 저장 중 오류: {e}"
                )

        # 진입하자마자 첫 번째 상태 메시지 전송
        sse_response = SSEResponse.create_discussion_status(
            "토론 참여 전문가들이 자료를 수집하는 중...", done=False
        )
        yield await sse_response.send()

        # 도구 목록 가져오기 (setup_node에서 설정됨)
        tools = state.get("tools")

        # 도구가 지정되지 않았으면 모든 도구 활성화 (기본값)
        if tools is None or len(tools) == 0:
            tools = [
                "gemini_web_search",
                "llm_knowledge",
                "internal_knowledge",
            ]

        # 도구 이름 매핑 (내부 이름 -> 표시 이름)
        tool_display_names = {
            "gemini_web_search": "웹검색",
            "llm_knowledge": "LLM",
            "internal_knowledge": "사내지식",
        }

        # 각 speaker-tool 조합별로 개별 자료 수집 태스크 생성
        # 각 tool의 완료 시점을 추적하기 위해 각 tool을 개별 태스크로 분리
        async def collect_single_tool_materials(speaker, tool_name, tool_display):
            """단일 speaker의 단일 tool 자료 수집"""
            # 해당 tool만 활성화하여 자료 수집
            single_tool_list = [tool_name]
            single_speaker_list = [speaker]
            result = await self.discussion.get_discussion_materials(
                topic=topic,
                speakers=single_speaker_list,
                state=state,
                tools=single_tool_list,
            )
            return speaker.get("speaker", ""), tool_display, result

        # 각 speaker-tool 조합별 태스크 생성
        tool_tasks_list = []
        for speaker in speakers:
            speaker_name = speaker.get("speaker", "")
            if not speaker_name:
                continue

            for tool in tools:
                if tool == "gemini_web_search":
                    tool_query_key = "web_search_query"
                elif tool == "llm_knowledge":
                    tool_query_key = "llm_search_query"
                elif tool == "internal_knowledge":
                    tool_query_key = "internal_search_query"
                else:
                    continue

                query = speaker.get(tool_query_key, "")
                if query:
                    tool_display = tool_display_names.get(tool, tool)
                    tool_tasks_list.append(
                        asyncio.create_task(
                            collect_single_tool_materials(speaker, tool, tool_display)
                        )
                    )

        # 완료된 tool부터 순서대로 처리
        materials_results = {}
        last_message_time = asyncio.get_event_loop().time()
        min_message_duration = 1.0  # 각 메시지 최소 표시 시간 (초)

        # 각 tool의 자료 수집이 완료되는 순서대로 처리
        for coro in asyncio.as_completed(tool_tasks_list):
            try:
                speaker_name, tool_display, result = await coro

                # 해당 speaker의 결과를 저장
                if speaker_name not in materials_results:
                    materials_results[speaker_name] = {
                        "materials": [],
                        "token_count": 0,
                        "response_second": 0.0,
                    }

                # 결과 합치기
                if isinstance(result, dict):
                    materials = result.get("materials", [])
                    if materials and len(materials) > 0:
                        materials_results[speaker_name]["materials"].extend(materials)
                    materials_results[speaker_name]["token_count"] += result.get(
                        "token_count", 0
                    )
                    materials_results[speaker_name]["response_second"] = max(
                        materials_results[speaker_name]["response_second"],
                        result.get("response_second", 0.0),
                    )

                # 해당 tool의 자료 수집 완료 메시지 전송
                # LLM 도구는 메시지를 표시하지 않음
                if tool_display != "LLM":
                    current_time = asyncio.get_event_loop().time()
                    # 이전 메시지와 최소 간격 유지
                    if current_time - last_message_time < min_message_duration:
                        await asyncio.sleep(
                            min_message_duration - (current_time - last_message_time)
                        )

                    # 더 긴 문구로 자료 수집 상태 표시
                    status_message = f"{speaker_name}가 {tool_display}을 통해 토론에 필요한 관련 자료를 수집하고 있습니다..."
                    sse_response = SSEResponse.create_discussion_status(
                        status_message, done=False
                    )
                    yield await sse_response.send()
                    last_message_time = asyncio.get_event_loop().time()

            except Exception as e:
                self.logger.error(f"Tool 자료 수집 중 오류: {e}")

        # 모든 자료 수집 결과를 합치기
        all_materials = []
        total_token_count = 0
        max_response_second = 0.0

        for speaker_name in [
            s.get("speaker", "") for s in speakers if s.get("speaker", "")
        ]:
            if speaker_name in materials_results:
                result = materials_results[speaker_name]
                materials = result.get("materials", [])
                if materials and len(materials) > 0:
                    # materials는 리스트이고, 각 항목은 {"speaker": ..., "materials": [...]} 형태
                    # 중복 제거를 위해 speaker별로 그룹화
                    speaker_materials_dict = {}
                    for material_item in materials:
                        if (
                            isinstance(material_item, dict)
                            and "speaker" in material_item
                        ):
                            mat_speaker = material_item.get("speaker", "")
                            if mat_speaker not in speaker_materials_dict:
                                speaker_materials_dict[mat_speaker] = material_item
                            else:
                                # 기존 materials에 추가
                                existing_mats = speaker_materials_dict[mat_speaker].get(
                                    "materials", []
                                )
                                new_mats = material_item.get("materials", [])
                                speaker_materials_dict[mat_speaker]["materials"].extend(
                                    new_mats
                                )

                    # 그룹화된 materials를 all_materials에 추가
                    for mat_item in speaker_materials_dict.values():
                        all_materials.append(mat_item)

                total_token_count += result.get("token_count", 0)
                max_response_second = max(
                    max_response_second, result.get("response_second", 0.0)
                )

        materials = all_materials
        token_count = total_token_count
        response_second = max_response_second

        self.logger.info(
            f"[DISCUSSION: 2. materials_completed] {len(materials)}개 자료 수집, token_count={token_count}, response_second={response_second}"
        )
        collector.log("discussion_materials", materials)

        # 상태 업데이트
        state["materials"] = materials

        # 마지막으로 done=True 메시지 전송
        sse_response = SSEResponse.create_discussion_status(
            "자료 수집이 완료되었습니다.", done=True
        )
        yield await sse_response.send()

    async def run_for_langgraph(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """LangGraph 호환을 위한 메서드 (상태 반환)"""
        self.logger.info("[DISCUSSION: 2. materials_start] 자료 수집 시작")

        # 토론 주제와 전문가 정보 가져오기
        topic = state.get("topic", "")
        speakers = state.get("speakers", [])

        if not topic or not speakers:
            self.logger.error(
                "[DISCUSSION: 2. materials_failed] 토론 주제 또는 전문가 정보 없음"
            )
            return {"materials": []}

        # 도구 목록 가져오기 (setup_node에서 설정됨)
        tools = state.get("tools")

        # 자료 수집 (state 전달하여 token 추적)
        materials_result = await self.discussion.get_discussion_materials(
            topic=topic,
            speakers=speakers,
            state=state,
            tools=tools,
        )

        # get_discussion_materials가 dict를 반환하므로 처리
        if isinstance(materials_result, dict):
            materials = materials_result.get("materials", [])
            token_count = materials_result.get("token_count", 0)
            response_second = materials_result.get("response_second", 0.0)
        else:
            # 기존 호환성을 위해 리스트도 처리
            materials = materials_result or []
            token_count = 0
            response_second = 0.0

        self.logger.info(
            f"[DISCUSSION: 2. materials_completed] {len(materials)}개 자료 수집, token_count={token_count}, response_second={response_second}"
        )

        return {
            "materials": materials or [],
            "token_count": token_count,
            "response_second": response_second,
        }
