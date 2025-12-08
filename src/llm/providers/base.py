"""
Base LLM Provider

LLM 프로바이더들의 공통 기본 클래스
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from src.llm.interfaces import (
    BaseLLMInterface,
    ChatMessage,
    ChatResponse,
    StreamingChatResponse,
)


class BaseLLMProvider(ABC):
    """LLM 프로바이더 기본 클래스"""

    def __init__(self, provider_name: str, config: Dict[str, Any]):
        """초기화

        Args:
            provider_name: 프로바이더 이름
            config: 프로바이더 설정
        """
        self.provider_name = provider_name
        self.config = config
        self.models: Dict[str, BaseLLMInterface] = {}
        self.default_model: Optional[str] = None

    @abstractmethod
    async def initialize(self) -> bool:
        """프로바이더 초기화"""
        pass

    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """사용 가능한 모델 목록 조회"""
        pass

    @abstractmethod
    async def create_model(
        self, model_name: str, config: Dict[str, Any]
    ) -> BaseLLMInterface:
        """모델 인스턴스 생성"""
        pass

    async def get_model(self, model_name: str) -> Optional[BaseLLMInterface]:
        """모델 인스턴스 조회"""
        return self.models.get(model_name)

    async def set_default_model(self, model_name: str) -> bool:
        """기본 모델 설정"""
        if model_name in self.models:
            self.default_model = model_name
            return True
        return False

    async def chat(
        self, messages: List[ChatMessage], model_name: str = None, **kwargs
    ) -> ChatResponse:
        """채팅 응답 생성"""
        model = await self._get_target_model(model_name)
        if not model:
            raise ValueError(f"Model not available: {model_name or self.default_model}")

        return await model.chat(messages, **kwargs)

    async def stream_chat(
        self, messages: List[ChatMessage], model_name: str = None, **kwargs
    ) -> AsyncGenerator[StreamingChatResponse, None]:
        """스트리밍 채팅 응답 생성"""
        model = await self._get_target_model(model_name)
        if not model:
            raise ValueError(f"Model not available: {model_name or self.default_model}")

        async for response in model.stream_chat(messages, **kwargs):
            yield response

    async def generate_text(self, prompt: str, model_name: str = None, **kwargs) -> str:
        """텍스트 생성"""
        model = await self._get_target_model(model_name)
        if not model:
            raise ValueError(f"Model not available: {model_name or self.default_model}")

        return await model.generate_text(prompt, **kwargs)

    async def health_check(self) -> Dict[str, Any]:
        """프로바이더 헬스체크"""
        health_status = {
            "provider": self.provider_name,
            "status": "healthy",
            "models": {},
            "default_model": self.default_model,
        }

        for model_name, model in self.models.items():
            try:
                is_healthy = await model.health_check()
                health_status["models"][model_name] = {
                    "available": model.is_available(),
                    "healthy": is_healthy,
                }
            except Exception as e:
                health_status["models"][model_name] = {
                    "available": False,
                    "healthy": False,
                    "error": str(e),
                }

        return health_status

    async def close(self):
        """프로바이더 종료"""
        for model in self.models.values():
            await model.close()
        self.models.clear()

    async def _get_target_model(
        self, model_name: str = None
    ) -> Optional[BaseLLMInterface]:
        """대상 모델 조회"""
        target_model = model_name or self.default_model
        if not target_model:
            # 사용 가능한 첫 번째 모델 사용
            available_models = [
                name for name, model in self.models.items() if model.is_available()
            ]
            if available_models:
                target_model = available_models[0]

        return self.models.get(target_model) if target_model else None
