"""
LLM Node

범용 LLM 호출 노드
"""

from logging import getLogger
from typing import Any, Dict, Optional

from src.database.connection import get_db
from src.database.services.agent_services import agent_llm_config_service
from src.llm.interfaces import ChatMessage, ChatResponse
from src.llm.manager import llm_manager
from src.schemas.sse_response import SSEResponse

logger = getLogger("agents.llm_node")


class LLMNode:
    """범용 LLM 노드 - 단순한 텍스트 생성/변환용"""

    def __init__(self, name: str, config: Dict[str, Any]):
        """초기화

        Args:
            name: 노드 이름
            config: 노드 설정 (agent_id 또는 agent_code가 있으면 DB에서 조회)
        """
        self.name = name
        self.config = config

        # agent_id 또는 agent_code가 있으면 DB에서 설정 조회
        agent_id = config.get("agent_id")
        agent_code = config.get("agent_code")

        if agent_id or agent_code:
            try:
                db = next(get_db())
                try:
                    if agent_id:
                        llm_config = agent_llm_config_service.get_by_agent_id(
                            db, agent_id
                        )
                    else:
                        llm_config = agent_llm_config_service.get_by_agent_code(
                            db, agent_code
                        )

                    if not llm_config:
                        raise ValueError(
                            f"에이전트 LLM 설정을 찾을 수 없습니다. "
                            f"(agent_id={agent_id}, agent_code={agent_code})"
                        )

                    # DB에서 조회한 설정 사용
                    provider = llm_config.provider
                    model = llm_config.model
                    temperature = llm_config.temperature
                    max_tokens = llm_config.max_tokens

                    # config에서 오버라이드 가능하도록 설정
                    if config.get("provider") is not None:
                        provider = config.get("provider")
                    if config.get("model") is not None:
                        model = config.get("model")
                    if config.get("temperature") is not None:
                        temperature = config.get("temperature")
                    if config.get("max_tokens") is not None:
                        max_tokens = config.get("max_tokens")

                finally:
                    db.close()
            except Exception as e:
                logger.error(f"LLM 설정 로드 실패: {e}")
                raise
        else:
            # 기존 방식: config에서 직접 읽기
            provider = config.get("provider")
            model = config.get("model")
            temperature = config.get("temperature", 0.7)
            max_tokens = config.get("max_tokens")

        # 'default'는 매니저 기본값을 사용하도록 None 처리
        self.provider = None if (provider in (None, "default", "")) else provider
        self.model = None if (model in (None, "default", "")) else model
        self.temperature = temperature if temperature is not None else 0.7
        self.max_tokens = max_tokens

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """범용 LLM 노드 처리 - 단순한 텍스트 생성/변환용

        Args:
            input_data: 입력 데이터

        Returns:
            처리 결과
        """
        try:
            # 입력에서 메시지 추출
            messages = input_data.get("messages", [])
            if not messages:
                return {"error": "No messages provided"}

            # ChatMessage 객체로 변환
            chat_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    chat_messages.append(ChatMessage(**msg))
                elif isinstance(msg, ChatMessage):
                    chat_messages.append(msg)
                else:
                    chat_messages.append(ChatMessage(role="user", content=str(msg)))

            # LLM 호출
            response = await llm_manager.chat(
                messages=chat_messages,
                provider=self.provider,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # 결과 반환
            return {
                "node": self.name,
                "type": "llm_response",
                "content": response.content,
                "model": response.model_name,
                "usage": response.usage,
                "metadata": {
                    "provider": self.provider,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                },
            }

        except Exception as e:
            logger.error(f"LLM 노드 처리 실패: {e}")
            return {"node": self.name, "error": str(e), "type": "error"}

    async def stream_process(self, input_data: Dict[str, Any]):
        """범용 스트리밍 노드 처리 - 단순한 텍스트 생성/변환용"""
        try:
            messages = input_data.get("messages", [])
            if not messages:
                yield {"error": "No messages provided"}
                return

            # ChatMessage 객체로 변환
            chat_messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    chat_messages.append(ChatMessage(**msg))
                elif isinstance(msg, ChatMessage):
                    chat_messages.append(msg)
                else:
                    chat_messages.append(ChatMessage(role="user", content=str(msg)))

            # 스트리밍 LLM 호출
            async for response in llm_manager.stream_chat(
                messages=chat_messages,
                provider=self.provider,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            ):
                # SSEResponse 형식으로 한글자씩 스트리밍
                if response.content:
                    sse_response = SSEResponse.create_caia_streaming(
                        token=response.content, done=response.is_complete
                    )
                    yield {
                        "node": self.name,
                        "type": "llm_stream",
                        "sse_response": sse_response,
                        "content": response.content,
                        "is_complete": response.is_complete,
                        "model": response.model_name,
                    }
                else:
                    # 완료된 응답은 그대로 전달
                    yield {
                        "node": self.name,
                        "type": "llm_stream",
                        "content": response.content,
                        "is_complete": response.is_complete,
                        "model": response.model_name,
                    }

        except Exception as e:
            logger.error(f"LLM 노드 스트리밍 실패: {e}")
            yield {"node": self.name, "error": str(e), "type": "error"}

    def get_config(self) -> Dict[str, Any]:
        """노드 설정 조회"""
        return {
            "name": self.name,
            "type": "llm_node",
            "provider": self.provider,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


# # llm 구동 test
# async def test():
#     llm = LLMNode(name="test",
#             config={"provider": "openai", "model": "lgedap-gpt-5-chat", "temperature": 0.7, "max_tokens": 4092})
#
#     from typing import List
#     system_prompt = """\
#                 <system_prompt>
#                 당신은 RAIH(Reliability AI Helper)입니다.
#                 사용자의 질문에 대해, **주어진 analysis source에 근거하여** 사실에 입각한 정확한 정보를 제공하시오.
#                 이를 위해 아래의 지시사항을 따르시오.
#
#                 사용자 질문에 대해 조회된 문서와 데이터입니다:
#                 <analysis source>
#                     {context}
#                 </analysis source>
#
#                 현재까지 사용자(user)와 당신(assistant)의 대화 이력입니다. 대화의 흐름과 문맥을 반드시 고려하시오:
#                 <chat_history>
#                     {chat_history}
#                 </chat_history>
#
#                 <instruction>
#                     당신은 제품 또는 부품의 고장 관련 정보를 받아서 FMEA를 작성하는 역할을 해야한다
#                     정보가 없으면 알려달라고 한다
#                 </instruction>
#
#                 <constraints>
#                     - 제품 또는 부품의 이름을 확인하고 구동 원리를 파악한다
#                     - 주어진 정보에 고장메커니즘 관련 내용이 없으면 위의 구동원리를 바탕으로 주요 고장메커니즘 또는 고장모드를 몇가지 선정한다
#                     - FMEA 항목은 다음과 같이 정의한다
#                         [부품] [기능] [요구사항] [고장모드] [고장의영향] [심각도] [고장메커니즘] [발생도] [검출도] [RPN위험도]
#                         - 각 항목의 설명은 다음과 같다
#                             [부품] : FMEA를 진행하는 부품의 이름
#                             [기능] : 부품의 제품 또는 시스템 내에서의 역할
#                             [요구사항] : 기능을 만족스럽게 수행하기 위해 필요한 능력(스펙)
#                             [고장모드] : 아이템의 고장이 발현되는 방식, 증상 또는 유형 (단선, 단락, 마모, 박리, 성능 저하 등)
#                             [고장의 영향] : 고장으로 인해 기능에 생기는 문제를 설명
#                             [심각도] : 고장의 영향이 제품의 기능에 얼마나 심각한지를 1 ~ 10점으로 수치화
#                             [고장메커니즘] : 스트레스와 잠재적인 원인에 의하여 아이템에 특정 고장모드가 나타나는 과정(피로, 과열, 이온 마이그레이션, 확산 등)
#                                            해당 과정을 상세하게 설명
#                             [발생도] : 해당 고장이 발생할 가능성이 얼마나 되는지 추정하여 1~10점으로 수치화
#                             [검출도] : 제품 출시 전에 해당 고장을 검출할 확률로 1~10점으로 수치화 어려울수록 값이 크다
#                             [RPN위험도] : Risk Priority Number의 약자로 [심각도] x [발생도] x [검출도] 로 계산한다
#                     - 각 항목에 대한 결과를 나열한 후 추가로 표로 정리한다
#                     - 추가로 [변경점], [설계관리현황] 등의 자료가 주어지면 그를 바탕으로 더 상세하게 작성해야 한다
#                 </constraints>
#
#                 다음은 사용자 질문입니다! analysis source와 chat history를 참고하고, 지시사항을 준수하여 대화 문맥에 맞게 답변하시오:
#                 <question>
#                     {user_query}
#                 </question>
#                 </system_prompt>\
#                 """
#     user_query = "팬모터 고장 모드와 고장 메커니즘을 나열하고, 고장 모드별 FMEA 작성해줘"
#     guidance = (
#         "한국어로 간결하지만 충분히 구체적으로 작성하고, 필요한 경우 표나 리스트로 구조화하세요. "
#         "가정이 필요하면 명시하고, 불확실성이나 추가 필요 정보도 마지막에 정리하세요."
#     )
#     rendered = system_prompt.format(user_query=user_query,
#                                     context="",
#                                     chat_history="")
#     messages: List[Dict[str, str]] = [
#         {"role": "system", "content": rendered},
#         {"role": "system", "content": guidance},
#         {"role": "user", "content": user_query},
#     ]
#     llm_result = await llm.process({"messages": messages})
#
#     print(llm_result)
#
# import asyncio
# asyncio.run(test())
