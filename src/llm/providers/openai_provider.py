"""
OpenAI Provider

OpenAI API를 사용한 LLM 프로바이더
"""

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, List

from openai import AsyncAzureOpenAI
from openai import RateLimitError, APIError

from src.llm.interfaces import (
    BaseLLMInterface,
    ChatMessage,
    ChatResponse,
    StreamingChatResponse,
)
from src.llm.providers.base import BaseLLMProvider

logger = logging.getLogger("llm.openai")


class OpenAIModel(BaseLLMInterface):
    """OpenAI 모델 인터페이스"""

    def __init__(self, model_name: str, config: Dict[str, Any]):
        """초기화"""
        super().__init__(model_name, config)
        self.client = None
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url")
        self.organization = config.get("organization")
        self.api_version = config.get("api_version")
        # Responses API는 2025-03-01-preview 이상에서만 사용
        # (2025-01-01-preview는 Chat Completions 사용)
        if self.api_version:
            self.use_responses_api = str(self.api_version) >= "2025-03-01-preview"
        else:
            self.use_responses_api = False

    async def initialize(self) -> bool:
        """모델 초기화"""
        try:
            if not self.api_key:
                logger.error("OpenAI API key not provided")
                return False

            # Azure OpenAI 클라이언트: API 버전/엔드포인트는 클라이언트에서 설정
            # Connection pooling을 위한 timeout 설정
            import httpx
            timeout = httpx.Timeout(60.0, connect=10.0)  # 총 60초, 연결 10초
            http_client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            )
            
            self.client = AsyncAzureOpenAI(
                api_key=self.api_key,
                azure_endpoint=self.base_url,
                api_version=self.api_version,
                http_client=http_client,
            )

            # 간단한 테스트 요청으로 연결 확인
            await self.health_check()
            self.is_initialized = True
            logger.info(
                f"[OPENAI_PROVIDER] OpenAI model {self.model_name} initialized successfully"
            )
            return True

        except Exception as e:
            logger.error(f"[OPENAI_PROVIDER] OpenAI model initialization failed: {e}")
            return False

    async def chat(self, messages: List[ChatMessage], **kwargs) -> ChatResponse:
        """채팅 응답 생성 (재시도 로직 포함)"""
        if not self.is_initialized:
            raise RuntimeError("Model not initialized")

        max_retries = 3
        base_delay = 1.0  # 초기 대기 시간 (초)
        
        for attempt in range(max_retries):
            try:
                # 메시지 변환
                converted_messages = []
                for msg in messages:
                    converted = {"role": msg.role.value, "content": msg.content}
                    if msg.name:
                        converted["name"] = msg.name
                    if msg.function_call:
                        converted["function_call"] = msg.function_call
                    converted_messages.append(converted)

                # 응답 시간 측정 시작
                start_time = time.time()
                
                if self.use_responses_api:
                    # Responses API
                    response = await self.client.responses.create(
                        model=self.model_name, input=converted_messages, **kwargs
                    )
                    # 응답 시간 측정 종료
                    response_time = time.time() - start_time
                    
                    content_text = getattr(response, "output_text", None)
                    if not content_text:
                        try:
                            # fallback 파싱
                            content_text = response.output[0].content[0].text  # type: ignore[attr-defined]
                        except Exception:
                            content_text = ""
                    usage = getattr(response, "usage", None)
                    
                    # usage 필드 구성 (일관성 유지)
                    usage_dict = None
                    if usage:
                        input_tokens = getattr(usage, "input_tokens", None)
                        output_tokens = getattr(usage, "output_tokens", None)
                        total_tokens = getattr(usage, "total_tokens", None)
                        usage_dict = {
                            # 기존 호환성을 위한 필드
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": total_tokens,
                            # 새로운 일관된 필드명
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                        }
                    
                    return ChatResponse(
                        content=content_text or "",
                        model_name=self.model_name,
                        usage=usage_dict,
                        response_time=response_time,
                    )
                else:
                    # Chat Completions API
                    response = await self.client.chat.completions.create(
                        model=self.model_name, messages=converted_messages, **kwargs
                    )
                    # 응답 시간 측정 종료
                    response_time = time.time() - start_time
                    
                    # usage 필드 구성 (일관성 유지)
                    usage_dict = None
                    if response.usage:
                        usage_dict = {
                            # 기존 호환성을 위한 필드
                            "prompt_tokens": response.usage.prompt_tokens,
                            "completion_tokens": response.usage.completion_tokens,
                            "total_tokens": response.usage.total_tokens,
                            # 새로운 일관된 필드명
                            "input_tokens": response.usage.prompt_tokens,
                            "output_tokens": response.usage.completion_tokens,
                        }
                    
                    return ChatResponse(
                        content=response.choices[0].message.content or "",
                        model_name=self.model_name,
                        usage=usage_dict,
                        finish_reason=response.choices[0].finish_reason,
                        response_time=response_time,
                    )
                    
            except RateLimitError as e:
                # Rate limit 에러 처리
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt * base_delay
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"[OPENAI_PROVIDER] Rate limit error (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"[OPENAI_PROVIDER] Rate limit error after {max_retries} attempts: {e}")
                    raise
                    
            except APIError as e:
                # API 에러 처리 (일시적 에러인 경우 재시도)
                if attempt < max_retries - 1 and e.status_code and e.status_code >= 500:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"[OPENAI_PROVIDER] API error (attempt {attempt + 1}/{max_retries}), "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"[OPENAI_PROVIDER] API error: {e}")
                    raise
                    
            except Exception as e:
                # 기타 에러는 즉시 재발생
                logger.error(f"[OPENAI_PROVIDER] OpenAI chat failed: {e}")
                raise

    async def stream_chat(
        self, messages: List[ChatMessage], **kwargs
    ) -> AsyncGenerator[StreamingChatResponse, None]:
        """스트리밍 채팅 응답 생성"""
        if not self.is_initialized:
            raise RuntimeError("Model not initialized")

        try:
            import time
            
            # 메시지 변환
            converted_messages = []
            for msg in messages:
                converted = {"role": msg.role.value, "content": msg.content}
                if msg.name:
                    converted["name"] = msg.name
                if msg.function_call:
                    converted["function_call"] = msg.function_call
                converted_messages.append(converted)

            # 스트리밍 시작 시간 측정
            start_time = time.time()
            accumulated_content = ""
            final_chunk = None
            
            if self.use_responses_api:
                # Responses API 스트리밍
                stream = await self.client.responses.stream(
                    model=self.model_name, input=converted_messages, **kwargs
                )
                async for event in stream:
                    # 텍스트 델타 처리
                    try:
                        event_type = getattr(event, "type", None)
                        if event_type == "response.output_text.delta":
                            delta = getattr(event, "delta", "")
                            if delta:
                                accumulated_content += delta
                                yield StreamingChatResponse(
                                    content=delta,
                                    model_name=self.model_name,
                                    is_complete=False,
                                    response_time=None,  # 스트리밍 중에는 None
                                )
                    except Exception:
                        continue
                final = await stream.get_final_response()
                finish_reason = getattr(final, "status", None)
                usage = getattr(final, "usage", None)
                
                # 응답 시간 계산
                response_time = time.time() - start_time
                
                # usage 필드 구성 (일관성 유지)
                usage_dict = None
                if usage:
                    input_tokens = getattr(usage, "input_tokens", None)
                    output_tokens = getattr(usage, "output_tokens", None)
                    total_tokens = getattr(usage, "total_tokens", None)
                    usage_dict = {
                        # 기존 호환성을 위한 필드
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        # 새로운 일관된 필드명
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    }
                
                yield StreamingChatResponse(
                    content="",  # 빈 내용으로 변경하여 중복 방지
                    model_name=self.model_name,
                    is_complete=True,
                    finish_reason=finish_reason,
                    usage=usage_dict,
                    response_time=response_time,
                )
            else:
                # Chat Completions 스트리밍
                stream = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=converted_messages,
                    stream=True,
                    **kwargs,
                )
                async for chunk in stream:
                    # choices 리스트가 비어있지 않은지 확인
                    if chunk.choices and len(chunk.choices) > 0:
                        choice = chunk.choices[0]
                        if hasattr(choice, "delta") and choice.delta.content:
                            content = choice.delta.content
                            accumulated_content += content
                            yield StreamingChatResponse(
                                content=content,
                                model_name=self.model_name,
                                is_complete=False,
                                response_time=None,  # 스트리밍 중에는 None
                            )
                    # 최종 chunk 저장 (usage 정보 포함)
                    final_chunk = chunk

                # 응답 시간 계산
                response_time = time.time() - start_time

                # 최종 응답 생성 (안전하게 finish_reason 접근)
                finish_reason = None
                usage_dict = None
                if final_chunk:
                    if final_chunk.choices and len(final_chunk.choices) > 0:
                        finish_reason = getattr(final_chunk.choices[0], "finish_reason", None)
                    # usage 정보 추출
                    if hasattr(final_chunk, "usage") and final_chunk.usage:
                        usage_dict = {
                            # 기존 호환성을 위한 필드
                            "prompt_tokens": final_chunk.usage.prompt_tokens,
                            "completion_tokens": final_chunk.usage.completion_tokens,
                            "total_tokens": final_chunk.usage.total_tokens,
                            # 새로운 일관된 필드명
                            "input_tokens": final_chunk.usage.prompt_tokens,
                            "output_tokens": final_chunk.usage.completion_tokens,
                        }

                yield StreamingChatResponse(
                    content="",  # 빈 내용으로 변경하여 중복 방지
                    model_name=self.model_name,
                    is_complete=True,
                    finish_reason=finish_reason,
                    usage=usage_dict,
                    response_time=response_time,
                )
        except Exception as e:
            logger.error(f"[OPENAI_PROVIDER] OpenAI stream chat failed: {e}")
            raise

    async def generate_text(self, prompt: str, **kwargs) -> str:
        """텍스트 생성"""
        if not self.is_initialized:
            raise RuntimeError("Model not initialized")

        try:
            if self.use_responses_api:
                response = await self.client.responses.create(
                    model=self.model_name,
                    input=[{"role": "user", "content": prompt}],
                    **kwargs,
                )
                content_text = getattr(response, "output_text", None)
                if content_text:
                    return content_text
                try:
                    return response.output[0].content[0].text  # type: ignore[attr-defined]
                except Exception:
                    return ""
            else:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    **kwargs,
                )
                return response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"[OPENAI_PROVIDER] OpenAI text generation failed: {e}")
            raise

    async def get_model_info(self) -> Dict[str, Any]:
        """모델 정보 조회"""
        return {
            "provider": "openai",
            "model_name": self.model_name,
            "capabilities": ["chat", "streaming", "text_generation"],
            "max_tokens": 8192,  # GPT-4 기준
            "supports_functions": True,
        }

    async def health_check(self) -> bool:
        """모델 헬스체크"""
        try:
            if not self.client:
                return False
            # 간단한 요청으로 연결 확인
            if self.use_responses_api:
                response = await self.client.responses.create(
                    model=self.model_name,
                    input=[{"role": "user", "content": "test"}],
                    max_output_tokens=5,
                )
                content_text = getattr(response, "output_text", None)
                return bool(content_text)
            else:
                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": "test"}],
                    max_tokens=5,
                )
                return bool(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"[OPENAI_PROVIDER] OpenAI health check failed: {e}")
            return False


class OpenAIProvider(BaseLLMProvider):
    """OpenAI 프로바이더"""

    def __init__(self, config: Dict[str, Any]):
        """초기화"""
        super().__init__("openai", config)
        
        # DB에서 agent_llm_config 읽어서 설정 병합
        db_config = self._load_config_from_db()
        if db_config:
            # DB 설정이 있으면 병합 (DB 설정이 우선)
            config = {**config, **db_config}
            # config 객체도 업데이트
            self.config.update(db_config)
            logger.info(
                f"[OPENAI_PROVIDER] DB 설정 병합 완료 - deployment: {db_config.get('deployment')}, "
                f"config deployment: {self.config.get('deployment')}"
            )
        
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url")
        self.organization = config.get("organization")
        self.api_version = config.get("api_version")

    def _load_config_from_db(self) -> Dict[str, Any]:
        """
        agent_llm_config 테이블에서 LLM 설정을 읽어서 반환합니다.
        DB 연결이 불가능한 경우 빈 딕셔너리를 반환합니다.
        """
        try:
            from src.database.connection import get_db
            from src.database.models.agent import AgentLLMConfig

            db = next(get_db())
            try:
                # provider가 "openai"인 활성화된 LLM 설정 조회
                llm_configs = (
                    db.query(AgentLLMConfig)
                    .filter(
                        AgentLLMConfig.provider == "openai",
                        AgentLLMConfig.is_active == True,
                    )
                    .all()
                )

                if not llm_configs:
                    logger.debug("[OPENAI_PROVIDER] agent_llm_config에서 openai 설정을 찾을 수 없습니다.")
                    return {}

                # 첫 번째 설정 사용
                llm_config = llm_configs[0]
                config_json = llm_config.config_json or {}
                
                logger.debug(
                    f"[OPENAI_PROVIDER] DB 설정 로드 - model={llm_config.model}, "
                    f"config_json keys={list(config_json.keys())}, "
                    f"deployment={config_json.get('deployment')}"
                )
                
                # 설정 딕셔너리 구성
                db_config = {}
                
                if config_json.get("api_key"):
                    db_config["api_key"] = config_json["api_key"]
                if config_json.get("base_url"):
                    db_config["base_url"] = config_json["base_url"]
                if config_json.get("api_version"):
                    db_config["api_version"] = config_json["api_version"]
                if config_json.get("deployment"):
                    db_config["deployment"] = config_json["deployment"]
                if config_json.get("organization"):
                    db_config["organization"] = config_json["organization"]
                
                # model 필드도 설정에 추가
                if llm_config.model:
                    db_config["model_name"] = llm_config.model
                    # deployment가 없으면 model을 deployment로 사용
                    if not db_config.get("deployment"):
                        db_config["deployment"] = llm_config.model

                logger.debug(
                    f"[OPENAI_PROVIDER] agent_llm_config에서 설정을 로드했습니다. "
                    f"(agent_id={llm_config.agent_id}, model={llm_config.model}, "
                    f"deployment={db_config.get('deployment')})"
                )
                
                return db_config

            finally:
                db.close()

        except Exception as e:
            # DB 연결 실패 시 무시
            logger.debug(f"[OPENAI_PROVIDER] agent_llm_config에서 설정을 로드할 수 없습니다: {e}")
            return {}

    async def initialize(self) -> bool:
        """프로바이더 초기화"""
        try:
            if not self.api_key:
                logger.error("[OPENAI_PROVIDER] OpenAI API key 없음")
                return False

            # deployment 우선순위: config의 deployment > model_name > 기본값
            deployment_name = (
                self.config.get("deployment")
                or self.config.get("model_name")
                or "gpt-5"
            )
            
            logger.info(
                f"[OPENAI_PROVIDER] 모델 초기화 시작 - deployment: {deployment_name}, "
                f"config keys: {list(self.config.keys())}"
            )
            
            default_models = [deployment_name]

            for model_name in default_models:
                model_config = {
                    "api_key": self.api_key,
                    "base_url": self.base_url,
                    "organization": self.organization,
                    "api_version": self.api_version,
                }

                model = OpenAIModel(model_name, model_config)
                if await model.initialize():
                    self.models[model_name] = model
                    if not self.default_model:
                        self.default_model = model_name
                    
                    # model 필드에 저장된 값(gpt-5 등)도 별칭으로 등록
                    # 실제 deployment 이름과 매핑
                    model_alias = self.config.get("model_name")
                    if model_alias and model_alias != model_name:
                        self.models[model_alias] = model
                        logger.info(
                            f"[OPENAI_PROVIDER] 모델 별칭 등록: {model_alias} -> {model_name}"
                        )

            logger.info(
                f"[OPENAI_PROVIDER] OpenAI provider initialized with {len(self.models)} models"
            )
            return len(self.models) > 0

        except Exception as e:
            logger.error(f"[OPENAI_PROVIDER] OpenAI 프로바이더 초기화 실패: {e}")
            return False

    async def get_available_models(self) -> List[str]:
        """사용 가능한 모델 목록 조회"""
        return list(self.models.keys())

    async def create_model(
        self, model_name: str, config: Dict[str, Any]
    ) -> BaseLLMInterface:
        """모델 인스턴스 생성"""
        model = OpenAIModel(model_name, config)
        if await model.initialize():
            self.models[model_name] = model
            return model
        else:
            raise RuntimeError(
                f"[OPENAI_PROVIDER] OpenAI 모델 초기화 실패: {model_name}"
            )
