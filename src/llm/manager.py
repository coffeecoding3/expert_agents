"""
LLM Manager

여러 LLM 프로바이더를 통합 관리하는 매니저
"""

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Match
import re

from .interfaces import ChatMessage, ChatResponse, StreamingChatResponse
from .providers import OpenAIProvider
from .rate_limiter import RateLimiter
from .priority_queue import PriorityQueue
from ..utils.lgenie_logger import lgenie_logger

logger = logging.getLogger("llm.manager")


class LLMManager:
    """LLM 매니저"""

    def __init__(self):
        """초기화"""
        self.providers: Dict[str, Any] = {}
        self.default_provider: Optional[str] = None
        self.default_model: Optional[str] = None
        self.is_initialized = False
        
        # 동시성 제어 관련
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.rate_limiter: Optional[RateLimiter] = None
        self.priority_queue: Optional[PriorityQueue] = None
        self.enable_priority_queue = False
        
        # 성능 모니터링
        self.total_requests = 0
        self.total_wait_time = 0.0
        self.active_requests = 0

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """LLM 매니저 초기화"""
        try:
            # 동시성 제어 설정 로드
            concurrency_config = config.get("concurrency", {})
            max_concurrent = concurrency_config.get("max_concurrent_requests", 50)
            rate_limit_per_minute = concurrency_config.get("rate_limit_per_minute", 500000)
            self.enable_priority_queue = concurrency_config.get("enable_priority_queue", True)
            priority_config = concurrency_config.get("priority_config", {})
            
            # Semaphore 초기화
            self.semaphore = asyncio.Semaphore(max_concurrent)
            logger.info(f"[LLM_MANAGER] Semaphore 초기화: max_concurrent={max_concurrent}")
            
            # Rate Limiter 초기화
            self.rate_limiter = RateLimiter(rate_limit_per_minute)
            logger.info(f"[LLM_MANAGER] Rate Limiter 초기화: rate_limit_per_minute={rate_limit_per_minute}")
            
            # 우선순위 큐 초기화
            if self.enable_priority_queue:
                self.priority_queue = PriorityQueue(priority_config)
                logger.info(f"[LLM_MANAGER] Priority Queue 초기화: priority_config={priority_config}")
            
            # OpenAI 프로바이더 초기화
            providers_config = config.get("providers", {})
            if "openai" in providers_config:
                openai_config = providers_config["openai"]
                if openai_config.get("api_key"):
                    openai_provider = OpenAIProvider(openai_config)
                    if await openai_provider.initialize():
                        self.providers["openai"] = openai_provider
                        logger.info(
                            "[LLM_MANAGER] OpenAI 프로바이더가 초기화되었습니다"
                        )
                    else:
                        logger.warning(
                            "[LLM_MANAGER] OpenAI 프로바이더 초기화에 실패했습니다"
                        )
                else:
                    logger.warning("[LLM_MANAGER] OpenAI API 키가 제공되지 않았습니다")

            # 다른 프로바이더는 비활성화 (GPT 전용)

            # 기본 프로바이더 설정
            if self.providers:
                self.default_provider = list(self.providers.keys())[0]
                # 기본 모델 설정
                default_provider = self.providers[self.default_provider]
                available_models = await default_provider.get_available_models()
                if available_models:
                    self.default_model = available_models[0]

                self.is_initialized = True
                return True
            else:
                logger.error("[LLM_MANAGER] 초기화된 LLM 프로바이더가 없습니다")
                return False

        except Exception as e:
            logger.error(f"[LLM_MANAGER] LLM 매니저 초기화에 실패했습니다: {e}")
            return False

    async def chat(
        self,
        messages: List[ChatMessage],
        provider: str = None,
        model: str = None,
        task_type: Optional[str] = None,
        human_message: Optional[str] = None,
        user_id: Optional[str] = None,
        chat_group_id: Optional[str] = None,
        **kwargs,
    ) -> ChatResponse:
        """채팅 응답 생성 (동시성 제어 포함)"""
        if not self.is_initialized:
            raise RuntimeError("LLM Manager not initialized")

        target_provider = provider or self.default_provider
        if target_provider not in self.providers:
            raise ValueError(f"Provider not available: {target_provider}")

        # 요청 시작 시간
        request_start_time = time.time()
        request_id = str(uuid.uuid4())[:8]
        
        # 요청 로깅
        effective_model = (
            model
            or getattr(self.providers[target_provider], "default_model", None)
            or self.default_model
        )
        try:
            logger.info(
                "[LLM_MANAGER] LLM chat request | request_id=%s provider=%s model=%s task_type=%s kwargs=%s",
                request_id,
                target_provider,
                effective_model,
                task_type,
                self._summarize_kwargs(kwargs),
            )
            logger.debug(
                "[LLM_MANAGER] LLM chat request messages | request_id=%s messages=%s",
                request_id,
                self._summarize_messages_for_log(messages),
            )
        except Exception as e:
            logger.warning(f"[LLM_MANAGER] 요청 로깅 실패: {e}")

        # 동시성 제어: Semaphore, Rate Limiter, 우선순위 큐
        wait_start_time = time.time()
        
        # Rate Limiter 체크 및 대기
        if self.rate_limiter:
            await self.rate_limiter.wait_if_needed()
        
        # Semaphore로 동시 요청 수 제한
        if self.semaphore:
            async with self.semaphore:
                self.active_requests += 1
                try:
                    wait_time = time.time() - wait_start_time
                    if wait_time > 0.1:  # 0.1초 이상 대기한 경우만 로깅
                        logger.info(
                            f"[LLM_MANAGER] Request acquired semaphore | request_id={request_id} wait_time={wait_time:.2f}s active_requests={self.active_requests}"
                        )
                    self.total_wait_time += wait_time
                    
                    # 실제 LLM 호출
                    response = await self.providers[target_provider].chat(messages, model, **kwargs)
                finally:
                    self.active_requests -= 1
        else:
            # Semaphore가 없으면 직접 호출
            response = await self.providers[target_provider].chat(messages, model, **kwargs)
        
        response.content = self._convert_equations_to_latex(response.content)
        
        # 성능 통계 업데이트
        total_time = time.time() - request_start_time
        self.total_requests += 1

        # 응답 로깅
        try:
            logger.info(
                "[LLM_MANAGER] LLM chat response | request_id=%s provider=%s model=%s usage=%s finish=%s total_time=%.2fs",
                request_id,
                target_provider,
                effective_model,
                getattr(response, "usage", None),
                getattr(response, "finish_reason", None),
                total_time,
            )
            logger.debug(
                "[LLM_MANAGER] LLM chat response content | request_id=%s content=%s",
                request_id,
                self._truncate_for_log(response.content),
            )

            await lgenie_logger(response = response,
                          request_start_time = request_start_time,
                          total_time = total_time,
                          user_id= user_id,
                          chat_group_id= chat_group_id,
                          human_message=human_message,
            )

        except Exception as e:
            logger.warning(f"[LLM_MANAGER] 응답 로깅 실패: {e}")

        return response

    async def stream_chat(
        self,
        messages: List[ChatMessage],
        provider: str = None,
        model: str = None,
        task_type: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[StreamingChatResponse, None]:
        """스트리밍 채팅 응답 생성 (동시성 제어 포함)"""
        if not self.is_initialized:
            raise RuntimeError("LLM Manager not initialized")

        target_provider = provider or self.default_provider
        if target_provider not in self.providers:
            raise ValueError(f"Provider not available: {target_provider}")

        # 요청 시작 시간
        request_start_time = time.time()
        request_id = str(uuid.uuid4())[:8]
        
        # 요청 로깅
        effective_model = (
            model
            or getattr(self.providers[target_provider], "default_model", None)
            or self.default_model
        )
        try:
            logger.debug(
                "[LLM_MANAGER] LLM stream_chat request | request_id=%s provider=%s model=%s task_type=%s kwargs=%s messages=%s",
                request_id,
                target_provider,
                effective_model,
                task_type,
                self._summarize_kwargs(kwargs),
                self._summarize_messages_for_log(messages),
            )
        except Exception:
            pass

        # 동시성 제어: Semaphore, Rate Limiter
        wait_start_time = time.time()
        
        # Rate Limiter 체크 및 대기
        if self.rate_limiter:
            await self.rate_limiter.wait_if_needed()
        
        # Semaphore로 동시 요청 수 제한
        if self.semaphore:
            async with self.semaphore:
                self.active_requests += 1
                try:
                    wait_time = time.time() - wait_start_time
                    if wait_time > 0.1:  # 0.1초 이상 대기한 경우만 로깅
                        logger.info(
                            f"[LLM_MANAGER] Stream request acquired semaphore | request_id={request_id} wait_time={wait_time:.2f}s active_requests={self.active_requests}"
                        )
                    self.total_wait_time += wait_time
                    
                    accumulated_content_parts: List[str] = []
                    async for response in self.providers[target_provider].stream_chat(
                        messages, model, **kwargs
                    ):
                        try:
                            if response.content:
                                accumulated_content_parts.append(response.content)
                                # 원본 토큰을 그대로 전달 (한글자씩 분해하지 않음)
                                yield StreamingChatResponse(
                                    content=response.content,
                                    model_name=response.model_name,
                                    is_complete=False,
                                )
                        except Exception:
                            pass
                        # 완료된 응답은 그대로 전달
                        if response.is_complete:
                            yield response
                finally:
                    self.active_requests -= 1
                    self.total_requests += 1
                    total_time = time.time() - request_start_time
                    logger.debug(
                        f"[LLM_MANAGER] Stream request completed | request_id={request_id} total_time={total_time:.2f}s"
                    )
        else:
            # Semaphore가 없으면 직접 호출
            accumulated_content_parts: List[str] = []
            async for response in self.providers[target_provider].stream_chat(
                messages, model, **kwargs
            ):
                try:
                    if response.content:
                        accumulated_content_parts.append(response.content)
                        # 원본 토큰을 그대로 전달 (한글자씩 분해하지 않음)
                        yield StreamingChatResponse(
                            content=response.content,
                            model_name=response.model_name,
                            is_complete=False,
                        )
                except Exception:
                    pass
                # 완료된 응답은 그대로 전달
                if response.is_complete:
                    yield response

    async def generate_text(
        self, prompt: str, provider: str = None, model: str = None, **kwargs
    ) -> str:
        """텍스트 생성"""
        if not self.is_initialized:
            raise RuntimeError("LLM Manager not initialized")

        target_provider = provider or self.default_provider
        if target_provider not in self.providers:
            raise ValueError(f"Provider not available: {target_provider}")

        # 요청 로깅
        effective_model = (
            model
            or getattr(self.providers[target_provider], "default_model", None)
            or self.default_model
        )
        try:
            logger.debug(
                "[LLM_MANAGER] LLM generate_text request | provider=%s model=%s kwargs=%s prompt=%s",
                target_provider,
                effective_model,
                self._summarize_kwargs(kwargs),
                self._truncate_for_log(prompt),
            )
        except Exception:
            pass

        text = await self.providers[target_provider].generate_text(
            prompt, model, **kwargs
        )

        # 응답 로깅
        try:
            logger.debug(
                "[LLM_MANAGER] LLM generate_text response | provider=%s model=%s text=%s",
                target_provider,
                effective_model,
                self._truncate_for_log(text),
            )
        except Exception:
            pass

        return text

    async def get_available_providers(self) -> List[str]:
        """사용 가능한 프로바이더 목록 조회"""
        return list(self.providers.keys())

    async def get_available_models(self, provider: str = None) -> Dict[str, List[str]]:
        """사용 가능한 모델 목록 조회"""
        if provider:
            if provider not in self.providers:
                return {}
            return {provider: await self.providers[provider].get_available_models()}

        models = {}
        for provider_name, provider_instance in self.providers.items():
            models[provider_name] = await provider_instance.get_available_models()
        return models

    async def set_default_provider(self, provider: str) -> bool:
        """기본 프로바이더 설정"""
        if provider in self.providers:
            self.default_provider = provider
            # 기본 모델도 업데이트
            default_provider = self.providers[provider]
            available_models = await default_provider.get_available_models()
            if available_models:
                self.default_model = available_models[0]
            return True
        return False

    async def set_default_model(self, provider: str, model: str) -> bool:
        """기본 모델 설정"""
        if provider in self.providers:
            provider_instance = self.providers[provider]
            if await provider_instance.set_default_model(model):
                if provider == self.default_provider:
                    self.default_model = model
                return True
        return False

    async def health_check(self) -> Dict[str, Any]:
        """전체 헬스체크"""
        if not self.is_initialized:
            return {"status": "not_initialized"}

        health_status = {
            "status": "healthy",
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "providers": {},
            "concurrency": {
                "active_requests": self.active_requests,
                "total_requests": self.total_requests,
                "avg_wait_time": (
                    self.total_wait_time / self.total_requests
                    if self.total_requests > 0
                    else 0.0
                ),
            },
        }
        
        # Rate Limiter 통계
        if self.rate_limiter:
            health_status["concurrency"]["current_rate"] = self.rate_limiter.get_current_rate()
        
        # Priority Queue 통계
        if self.priority_queue:
            health_status["concurrency"]["priority_queue"] = self.priority_queue.get_stats()

        for provider_name, provider_instance in self.providers.items():
            try:
                provider_health = await provider_instance.health_check()
                health_status["providers"][provider_name] = provider_health

                if provider_health.get("status") != "healthy":
                    health_status["status"] = "degraded"

            except Exception as e:
                health_status["providers"][provider_name] = {
                    "status": "error",
                    "error": str(e),
                }
                health_status["status"] = "degraded"

        return health_status

    async def get_provider_info(self, provider: str = None) -> Dict[str, Any]:
        """프로바이더 정보 조회"""
        if provider:
            if provider not in self.providers:
                return {"error": f"Provider not found: {provider}"}
            return await self.providers[provider].health_check()

        info = {
            "total_providers": len(self.providers),
            "default_provider": self.default_provider,
            "default_model": self.default_model,
            "providers": {},
        }

        for provider_name, provider_instance in self.providers.items():
            info["providers"][provider_name] = {
                "available_models": await provider_instance.get_available_models(),
                "default_model": provider_instance.default_model,
            }

        return info

    async def close(self):
        """LLM 매니저 종료"""
        for provider in self.providers.values():
            await provider.close()

        self.providers.clear()
        self.is_initialized = False
        logger.info("[LLM_MANAGER] LLM 매니저가 종료되었습니다")

    # 내부: 로그 보조 유틸리티
    def _truncate_for_log(self, text: Any, max_len: int = 2000) -> Any:
        try:
            if text is None:
                return None
            s = str(text)
            return s if len(s) <= max_len else s[:max_len] + "…(truncated)"
        except Exception:
            return text

    def _summarize_messages_for_log(
        self, messages: List[ChatMessage], max_len_each: int = 1000
    ) -> List[Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        try:
            for m in messages:
                summary.append(
                    {
                        "role": getattr(m.role, "value", str(getattr(m, "role", ""))),
                        "content": self._truncate_for_log(
                            getattr(m, "content", ""), max_len_each
                        ),
                        "name": getattr(m, "name", None),
                    }
                )
        except Exception:
            return []
        return summary

    def _summarize_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            sanitized = dict(kwargs)
            # 잠재적으로 큰 값 제거/축약
            for key in ["functions", "tools", "response_format"]:
                if key in sanitized:
                    sanitized[key] = "<omitted>"
            # 수치값/간단 문자열은 그대로 두고, 긴 문자열은 절단
            for k, v in list(sanitized.items()):
                if isinstance(v, str):
                    sanitized[k] = self._truncate_for_log(v, 200)
            return sanitized
        except Exception:
            return {}


    def _convert_equations_to_latex(self, text: str) -> str:
        # \[ ... \] 블록 찾기
        # math_block_pattern = re.compile(r"\\\[(?P<content>.+?)\\\]", re.DOTALL)
        math_pattern = re.compile(r"(\\\[.*?\\\]|\\\(.*?\\\))", re.DOTALL)

        # LaTeX 명령어 (\frac, \sqrt 등)만 찾아서 이스케이프
        latex_command_pattern = re.compile(r'\\[a-zA-Z]+')

        def _escape_latex_commands(s: str) -> str:
            return latex_command_pattern.sub(lambda m: "\\" + m.group(0), s)

        def _replace_math(m: Match[str]) -> str:
            raw = m.group(0)
            if raw.startswith(r"\[") and raw.endswith(r"\]"):
                inner = raw[2:-2].strip()
            elif raw.startswith(r"\(") and raw.endswith(r"\)"):
                inner = raw[2:-2].strip()
            else:
                return raw

            # 1. 유니코드 특수 문자를 LaTeX 명령어로 치환
            # 자주 쓰이는 유니코드 연산자 치환
            inner = inner.replace("×", "\\times")
            inner = inner.replace("≈", "\\approx")

            # 유니코드 위첨자 치환
            superscripts = {
                "⁰": "^0", "¹": "^1", "²": "^2", "³": "^3", "⁴": "^4",
                "⁵": "^5", "⁶": "^6", "⁷": "^7", "⁸": "^8", "⁹": "^9"
            }
            for char, latex in superscripts.items():
                inner = inner.replace(char, latex)

            # 2. 줄바꿈 처리 및 aligned 환경 적용
            if '\n' in inner and r"\begin" not in inner:
                # 개행 문자(\n)를 LaTeX 줄바꿈 명령(\\)으로 변경
                # KaTeX 호환성을 위해 공백을 둠 (r' \\ ')
                inner = inner.replace('\n', r' \\ ')
                inner = "\\begin{aligned}" + inner + "\\end{aligned}"


            return f"$${inner}$$"

        return math_pattern.sub(_replace_math, text)

# 전역 LLM 매니저 인스턴스
llm_manager = LLMManager()
