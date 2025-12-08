"""
Base LLM Interface

LLM 모델들의 공통 인터페이스
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from .chat import ChatMessage, ChatResponse, StreamingChatResponse


class BaseLLMInterface(ABC):
    """LLM 기본 인터페이스"""

    def __init__(self, model_name: str, config: Dict[str, Any]):
        """초기화

        Args:
            model_name: 모델 이름
            config: 모델 설정
        """
        self.model_name = model_name
        self.config = config
        self.is_initialized = False

    @abstractmethod
    async def initialize(self) -> bool:
        """모델 초기화"""
        pass

    @abstractmethod
    async def chat(self, messages: List[ChatMessage], **kwargs) -> ChatResponse:
        """채팅 응답 생성"""
        pass

    @abstractmethod
    async def stream_chat(
        self, messages: List[ChatMessage], **kwargs
    ) -> AsyncGenerator[StreamingChatResponse, None]:
        """스트리밍 채팅 응답 생성"""
        pass

    @abstractmethod
    async def generate_text(self, prompt: str, **kwargs) -> str:
        """텍스트 생성"""
        pass

    @abstractmethod
    async def get_model_info(self) -> Dict[str, Any]:
        """모델 정보 조회"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """모델 헬스체크"""
        pass

    async def close(self):
        """모델 연결 종료"""
        self.is_initialized = False

    def is_available(self) -> bool:
        """모델 사용 가능 여부"""
        return self.is_initialized

    def get_config(self) -> Dict[str, Any]:
        """모델 설정 조회"""
        return self.config.copy()
