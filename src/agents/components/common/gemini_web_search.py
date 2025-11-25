"""
Web Search Component using Google Gemini

Gemini 기반 웹 서치 컴포넌트
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from google import genai
from google.genai import types

from src.utils.config_utils import ConfigUtils
from src.utils.result_utils import (
    create_web_search_error_result,
    create_web_search_success_result,
)

logger = logging.getLogger("agents.components.gemini_web_search")


class GeminiWebSearch:
    """웹 서치 컴포넌트 - Gemini 기반"""

    # 상수
    REDIRECT_TIMEOUT = 10
    MODEL_NAME = "gemini-2.5-flash-lite"
    # MODEL_NAME = "gemini-2.5-flash",
    # MODEL_NAME = "gemini-2.5-pro",

    # API 키 환경 변수 이름
    ENV_GEMINI_API_KEY = "GEMINI_API_KEY"
    ENV_GOOGLE_API_KEY = "GOOGLE_API_KEY"

    name = "gemini_web_search"
    description = "웹 검색을 수행합니다"

    def __init__(self):
        """초기화"""
        self.query: str = ""
        self.api_key: Optional[str] = self._load_api_key()
        self.client: Optional[genai.Client] = None
        self.config: Optional[types.GenerateContentConfig] = None
        self._initialize_client()

    def _load_api_key(self) -> Optional[str]:
        """API 키를 로드합니다. 환경 변수 우선, 설정 파일 차순."""
        api_key = ConfigUtils.get_api_key(
            key_name="Gemini API Key",
            env_var_names=[self.ENV_GEMINI_API_KEY, self.ENV_GOOGLE_API_KEY],
            config_path=[["google", "gemini", "api_key"], ["google", "api_key"]],
        )

        if api_key:
            logger.debug(f"[WEB_SEARCH] API 키 로드됨: {api_key[:10]}...")
        else:
            logger.warning(
                "[WEB_SEARCH] API 키가 설정되지 않았습니다. "
                f"환경 변수 {self.ENV_GEMINI_API_KEY} 또는 {self.ENV_GOOGLE_API_KEY}를 설정하거나 "
                "app.yaml의 google.gemini.api_key 또는 google.api_key를 설정하세요."
            )

        return api_key

    def _initialize_client(self) -> None:
        """Gemini 클라이언트와 설정을 초기화합니다."""
        if not self.api_key:
            self.client = None
            self.config = None
            return

        try:
            self.client = genai.Client(api_key=self.api_key)
            grounding_tool = types.Tool(google_search=types.GoogleSearch())
            self.config = types.GenerateContentConfig(tools=[grounding_tool])
        except Exception as e:
            logger.error(f"[WEB_SEARCH] 클라이언트 초기화 실패: {e}")
            self.client = None
            self.config = None

    def _is_client_ready(self) -> bool:
        """클라이언트가 사용 가능한지 확인합니다."""
        if not self.api_key or not self.client or not self.config:
            logger.error("[WEB_SEARCH] API 키 또는 클라이언트가 초기화되지 않았습니다.")
            return False
        return True

    def _create_error_result(self, error_message: str) -> Dict[str, Any]:
        """웹 검색 에러 결과를 생성합니다."""
        return create_web_search_error_result(error_message)

    def _create_success_result(
        self,
        search_queries: List[str],
        summary: str,
        reference_urls: List[str],
    ) -> Dict[str, Any]:
        """웹 검색 성공 결과를 생성합니다."""
        return create_web_search_success_result(search_queries, summary, reference_urls)

    def _generate_content(self, query: str) -> Any:
        """Gemini API를 호출하여 콘텐츠를 생성합니다."""
        return self.client.models.generate_content(
            model=self.MODEL_NAME,
            contents=query,
            config=self.config,
        )

    def _extract_grounding_metadata(self, response: Any) -> Optional[Any]:
        """응답에서 grounding metadata를 추출합니다."""
        if not response.candidates:
            return None

        candidate = response.candidates[0]
        if (
            not hasattr(candidate, "grounding_metadata")
            or not candidate.grounding_metadata
        ):
            return None

        return candidate.grounding_metadata

    def _extract_search_queries(self, grounding_metadata: Any) -> List[str]:
        """grounding metadata에서 검색 쿼리를 추출합니다."""
        if not hasattr(grounding_metadata, "web_search_queries"):
            return []
        return grounding_metadata.web_search_queries or []

    def _extract_redirect_urls(self, grounding_chunks: List[Any]) -> List[str]:
        """grounding chunks에서 리다이렉트 URL을 추출합니다."""
        return [
            chunk.web.uri
            for chunk in grounding_chunks
            if hasattr(chunk, "web") and chunk.web and hasattr(chunk.web, "uri")
        ]

    def _resolve_redirect_url(self, redirect_url: str) -> str:
        """리다이렉트 URL을 실제 URL로 변환합니다."""
        try:
            response = requests.get(
                redirect_url, allow_redirects=False, timeout=self.REDIRECT_TIMEOUT
            )
            location = response.headers.get("Location")
            return location if location else redirect_url
        except Exception as e:
            logger.debug(
                f"[WEB_SEARCH] URL 리다이렉트 처리 실패: {redirect_url}, 오류: {e}"
            )
            return redirect_url

    def _resolve_direct_urls(self, redirect_urls: List[str]) -> List[str]:
        """리다이렉트 URL 리스트를 실제 URL 리스트로 변환합니다."""
        return [self._resolve_redirect_url(url) for url in redirect_urls]

    def _process_search_response(self, response: Any) -> Dict[str, Any]:
        """검색 응답을 처리하여 결과를 반환합니다."""
        grounding_metadata = self._extract_grounding_metadata(response)
        summary = response.text if hasattr(response, "text") and response.text else ""

        # grounding metadata가 없는 경우
        if not grounding_metadata:
            logger.warning("[WEB_SEARCH] 검색 결과가 없습니다.")
            return self._create_success_result(
                search_queries=[],
                summary=summary,
                reference_urls=[],
            )

        # grounding chunks가 없는 경우
        grounding_chunks = grounding_metadata.grounding_chunks or []
        if not grounding_chunks:
            logger.warning("[WEB_SEARCH] 검색된 URL이 없습니다.")
            search_queries = self._extract_search_queries(grounding_metadata)
            return self._create_success_result(
                search_queries=search_queries,
                summary=summary,
                reference_urls=[],
            )

        # 정상적인 검색 결과 처리
        redirect_urls = self._extract_redirect_urls(grounding_chunks)
        direct_urls = self._resolve_direct_urls(redirect_urls)
        search_queries = self._extract_search_queries(grounding_metadata)

        result = self._create_success_result(
            search_queries=search_queries,
            summary=summary,
            reference_urls=direct_urls,
        )

        self._log_search_result(result)
        return result

    def _log_search_result(self, result: Dict[str, Any]) -> None:
        """검색 결과를 로깅합니다."""
        search_queries_count = len(result.get("search_queries", []))
        reference_count = len(result.get("reference", []))
        summary_length = len(result.get("summary", ""))

        logger.info(
            f"[WEB_SEARCH] 웹 검색 완료: "
            f"search_queries={search_queries_count}개, "
            f"reference={reference_count}개, "
            f"summary 길이={summary_length}자"
        )

    def web_search(self, query: str) -> Dict[str, Any]:
        """
        웹 서치를 수행합니다.

        Args:
            query: 사용자 쿼리

        Returns:
            분석 결과 딕셔너리:
            {
                "search_queries": List[str],  # 검색에 사용된 쿼리 목록
                "summary": str,              # 검색 결과 요약
                "reference": List[str]       # 참조 URL 목록
            }
        """
        self.query = query
        logger.info(f"[WEB_SEARCH] 웹 검색 시작: query='{query}'")

        if not self._is_client_ready():
            return self._create_error_result("API 키가 설정되지 않았습니다.")

        try:
            response = self._generate_content(query)
            return self._process_search_response(response)
        except Exception as e:
            logger.error(f"[WEB_SEARCH] 웹 검색 중 예외 발생: {e}", exc_info=True)
            return self._create_error_result(f"웹 검색 중 오류 발생: {str(e)}")

    async def run(self, query: str) -> Dict[str, Any]:
        """
        도구 인터페이스를 위한 비동기 run 메서드

        Args:
            query: 사용자 쿼리

        Returns:
            검색 결과 딕셔너리
        """
        return await asyncio.to_thread(self.web_search, query)
