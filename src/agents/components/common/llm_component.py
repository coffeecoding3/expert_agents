"""
LLM Component
공통 LLM 호출 컴포넌트 - 비즈니스 로직이 있는 LLM 호출을 위한 기본 클래스
"""

import json
from logging import getLogger
from typing import Any, Dict, List, Optional

from configs.app_config import load_config
from src.database.services.agent_services import agent_llm_config_service, agent_service
from src.utils.db_utils import get_db_session
from src.llm.interfaces import ChatMessage, ChatResponse
from src.llm.interfaces.chat import MessageRole
from src.llm.manager import llm_manager
from src.prompts.prompt_manager import prompt_manager

logger = getLogger("agents.llm_component")


class LLMComponent:
    """LLM 컴포넌트 기본 클래스"""

    def __init__(
        self, agent_id: Optional[int] = None, agent_code: Optional[str] = None
    ):
        """초기화

        Args:
            agent_id: 에이전트 ID (선택사항)
            agent_code: 에이전트 코드 (선택사항, agent_id가 없을 때 사용)
        """
        self.agent_id = agent_id
        self.agent_code = agent_code.upper() if agent_code else None
        self._llm_config = None
        self._load_llm_config()

    def _load_llm_config(self):
        """DB에서 LLM 설정 로드"""
        if not self.agent_id and not self.agent_code:
            raise ValueError("agent_id 또는 agent_code가 필요합니다.")

        try:
            with get_db_session() as db:
                if self.agent_id:
                    llm_config = agent_llm_config_service.get_by_agent_id(
                        db, self.agent_id
                    )
                else:
                    llm_config = agent_llm_config_service.get_by_agent_code(
                        db, self.agent_code
                    )
                    if llm_config:
                        self.agent_id = llm_config.agent_id

                if not llm_config:
                    raise ValueError(
                        f"에이전트 LLM 설정을 찾을 수 없습니다. "
                        f"(agent_id={self.agent_id}, agent_code={self.agent_code})"
                    )

                self._llm_config = llm_config

                # LLM 설정 파싱
                self.llm_provider = llm_config.provider if llm_config.provider else None
                self.llm_model = llm_config.model if llm_config.model else None
                self.temperature = (
                    llm_config.temperature
                    if llm_config.temperature is not None
                    else 0.7
                )
                self.max_tokens = llm_config.max_tokens

                # config_json에서 provider별 설정 추출 (필요시 사용)
                self.provider_config = llm_config.config_json or {}

        except Exception as e:
            logger.error(f"LLM 설정 로드 실패: {e}")
            raise

    async def chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """LLM 채팅 호출

        Args:
            messages: 채팅 메시지 목록
            temperature: 온도 설정 (None이면 기본값 사용)
            max_tokens: 최대 토큰 수 (None이면 기본값 사용)

        Returns:
            LLM 응답
        """
        return await llm_manager.chat(
            messages=messages,
            provider=self.llm_provider,
            model=self.llm_model,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

    async def chat_with_prompt(
        self,
        prompt_template: str,
        template_vars: Dict[str, Any],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """프롬프트 템플릿을 사용한 LLM 호출

        Args:
            prompt_template: 프롬프트 템플릿 이름
            template_vars: 템플릿 변수
            temperature: 온도 설정
            max_tokens: 최대 토큰 수

        Returns:
            LLM 응답
        """
        # 프롬프트 렌더링
        rendered = prompt_manager.render_template(prompt_template, template_vars)

        # 메시지 생성
        messages = [ChatMessage(role=MessageRole.USER, content=rendered)]

        # LLM 호출
        return await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """스트리밍 LLM 채팅 호출

        Args:
            messages: 채팅 메시지 목록
            temperature: 온도 설정
            max_tokens: 최대 토큰 수

        Yields:
            스트리밍 응답
        """
        async for response in llm_manager.stream_chat(
            messages=messages,
            provider=self.llm_provider,
            model=self.llm_model,
            temperature=temperature or self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        ):
            yield response

    async def stream_chat_with_prompt(
        self,
        prompt_template: str,
        template_vars: Dict[str, Any],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """프롬프트 템플릿을 사용한 스트리밍 LLM 호출

        Args:
            prompt_template: 프롬프트 템플릿 이름
            template_vars: 템플릿 변수
            temperature: 온도 설정
            max_tokens: 최대 토큰 수

        Yields:
            스트리밍 응답
        """
        # 프롬프트 렌더링
        rendered = prompt_manager.render_template(prompt_template, template_vars)

        # 메시지 생성
        messages = [ChatMessage(role=MessageRole.USER, content=rendered)]

        # 스트리밍 LLM 호출
        async for response in self.stream_chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield response

    def get_config(self) -> Dict[str, Any]:
        """컴포넌트 설정 조회"""
        return {
            "provider": self.llm_provider,
            "model": self.llm_model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
