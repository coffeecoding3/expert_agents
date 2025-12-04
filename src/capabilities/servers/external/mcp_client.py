"""
MCP (Model Context Protocol) Client
외부 MCP 서버와 통신하여 도구들을 사용할 수 있도록 하는 클라이언트
"""

import asyncio
import json
import uuid
import webbrowser
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from configs import app_config
from src.capabilities.logging_utils import ClientLogger
from src.capabilities.exceptions import (
    MCPClientError,
    MCPAuthenticationError,
    MCPNetworkError,
    MCPToolError,
)
from src.capabilities.constants import (
    MCP_PROTOCOL_VERSION,
    MCP_SSO_ID_HEADER,
    MCP_API_KEY_HEADER,
    DEFAULT_TIMEOUT,
    DEFAULT_RETRY_ATTEMPTS,
)
from src.schemas.raih_exceptions import (
    RAIHAuthorizationException,
    RAIHBusinessException,
)


@dataclass
class MCPTool:
    """MCP 도구 정보를 담는 데이터 클래스"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None


@dataclass
class MCPServerInfo:
    """MCP 서버 정보를 담는 데이터 클래스"""

    name: str
    version: str
    capabilities: Dict[str, Any]


class MCPClient:
    """MCP 클라이언트 - 외부 MCP 서버와 통신"""

    def __init__(
        self,
        endpoint: str,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
    ):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.headers = headers or {}
        self.timeout = timeout
        self.retry_attempts = retry_attempts

        # MCP 서버 정보
        self.server_info: Optional[MCPServerInfo] = None
        self.available_tools: List[MCPTool] = []
        self.initialized = False

        # HTTP 클라이언트
        self._client: Optional[httpx.AsyncClient] = None

        ClientLogger.debug("MCP 클라이언트 초기화", endpoint=self.endpoint)

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        await self.close()

    async def _ensure_client(self):
        """HTTP 클라이언트가 없으면 생성"""
        if self._client is None or self._client.is_closed:
            ClientLogger.debug("새로운 HTTP 클라이언트 생성 중")
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout), follow_redirects=True
            )
            ClientLogger.debug("HTTP 클라이언트 생성 완료", timeout=self.timeout)
        else:
            ClientLogger.debug("기존 HTTP 클라이언트 사용")

    async def close(self):
        """리소스 정리"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_headers(self, sso_id: Optional[str] = None) -> Dict[str, str]:
        """요청 헤더 생성"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            MCP_SSO_ID_HEADER: sso_id or "demo",
            "mcp-protocol-version": MCP_PROTOCOL_VERSION,
        }

        if self.api_key:
            api_key_header = self.headers.get("api_key", MCP_API_KEY_HEADER)
            headers[api_key_header] = self.api_key

        ClientLogger.debug(
            "헤더 생성 완료",
            sso_id=sso_id,
            has_api_key=bool(self.api_key),
        )
        return headers

    def _parse_sse_response(self, response_text: str) -> Dict[str, Any]:
        """SSE 형식 응답을 파싱하여 JSON 객체 반환"""
        lines = response_text.strip().split("\n")
        data_lines = [line[6:] for line in lines if line.strip().startswith("data: ")]

        if not data_lines:
            ClientLogger.error(
                "SSE 응답에서 data를 찾을 수 없습니다",
                response_length=len(response_text),
            )
            raise Exception("SSE 응답에서 data를 찾을 수 없습니다")

        try:
            result = json.loads(data_lines[0])
            ClientLogger.debug("SSE JSON 파싱 성공")
            return result
        except json.JSONDecodeError as e:
            ClientLogger.error("SSE JSON 파싱 실패", error=str(e), data=data_lines[0])
            raise Exception(f"SSE data JSON 파싱 실패: {e}")

    def _build_request_payload(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """MCP 요청 페이로드 구성"""
        payload = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method}

        if params:
            payload["params"] = params
        elif method == "initialize":
            payload["params"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "chief-ai-advisor", "version": "1.0.0"},
            }
        elif method == "tools/list":
            payload["params"] = {}

        # ClientLogger.debug("페이로드 구성 완료", method=method, has_params=bool(params))
        return payload

    def _parse_response(self, response: httpx.Response) -> Dict[str, Any]:
        """응답 파싱"""
        response_text = response.text
        if not response_text.strip():
            raise Exception("빈 응답을 받았습니다")

        # 응답 파싱
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/event-stream"):
            result = self._parse_sse_response(response_text)
        else:
            try:
                result = response.json()
            except Exception as e:
                ClientLogger.error("JSON 파싱 실패", error=str(e))
                raise

        # JSON-RPC 에러 체크
        if "error" in result:
            error = result["error"]
            error_msg = f"MCP Error {error.get('code', 'unknown')}: {error.get('message', 'Unknown error')}"
            ClientLogger.error("JSON-RPC 에러 발견", error=error)
            raise Exception(error_msg)

        final_result = result.get("result", {})
        ClientLogger.debug(
            "응답 파싱 완료",
            status_code=response.status_code,
            content_type=content_type,
        )
        return final_result

    async def _make_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        sso_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """MCP 서버에 요청을 보내고 응답을 받음"""
        await self._ensure_client()
        payload = self._build_request_payload(method, params)
        headers = self._get_headers(sso_id)

        # ClientLogger.debug("요청 시작", method=method, endpoint=self.endpoint)

        # 도구 호출인 경우 상세 로깅 (debug 레벨로 변경)
        if method == "tools/call" and params:
            tool_name = params.get("name", "unknown")
            tool_args = params.get("arguments", {})
            ClientLogger.debug(
                f"MCP 도구 호출 시작 - 도구: {tool_name}, SSO ID: {sso_id or 'None'}",
                tool_name=tool_name,
                arguments=tool_args,
                sso_id=sso_id,
            )

        # 인증 관련 재시도를 위한 별도 카운터
        auth_retry_count = 0
        max_auth_retries = 5  # 인증 관련 최대 재시도 횟수

        for attempt in range(self.retry_attempts):
            try:
                # ClientLogger.debug(
                #     f"요청 시도 {attempt + 1}/{self.retry_attempts}", method=method
                # )
                response = await self._client.post(
                    self.endpoint, json=payload, headers=headers
                )

                if response.status_code != 200:
                    error_msg = f"HTTP {response.status_code}: {response.text}"
                    ClientLogger.error(
                        "HTTP 요청 실패",
                        status_code=response.status_code,
                        response=response.text,
                    )
                    if response.status_code == 403:
                        auth_retry_count += 1
                        if auth_retry_count > max_auth_retries:
                            raise Exception(
                                f"인증 재시도 횟수 초과 ({max_auth_retries}회)"
                            )

                        redirect_url = app_config.get("mcp", "ms_office_redirect_url")
                        if redirect_url:
                            ClientLogger.info(
                                f"403 에러 발생, 리다이렉트 URL로 이동: {redirect_url} (인증 재시도 {auth_retry_count}/{max_auth_retries})"
                            )
                            # 리다이렉트 URL로 리다이렉트
                            webbrowser.open(redirect_url)

                            # 인증 완료를 기다리고 재시도
                            ClientLogger.info(
                                "인증 완료를 기다리는 중... (15초 후 자동 재시도)"
                            )
                            ClientLogger.info(
                                f"\n🔐 인증이 필요합니다! (재시도 {auth_retry_count}/{max_auth_retries})"
                            )
                            ClientLogger.info(
                                f"브라우저에서 {redirect_url}로 이동하여 인증을 완료해주세요."
                            )
                            ClientLogger.info(
                                "인증 완료 후 15초 후에 자동으로 재시도됩니다..."
                            )
                            ClientLogger.info(
                                "(또는 Enter 키를 눌러 즉시 재시도할 수 있습니다)\n"
                            )

                            # 사용자 입력을 기다리거나 15초 대기
                            try:
                                # 비동기적으로 사용자 입력을 기다림 (15초 타임아웃)
                                await asyncio.wait_for(
                                    asyncio.get_event_loop().run_in_executor(
                                        None, input
                                    ),
                                    timeout=15.0,
                                )
                                ClientLogger.info("사용자가 수동으로 재시도 선택")
                            except asyncio.TimeoutError:
                                ClientLogger.info("15초 타임아웃, 자동 재시도")

                            ClientLogger.info("인증 대기 완료, 재시도 중...")
                            continue  # 현재 시도를 건너뛰고 다음 시도로
                        else:
                            ClientLogger.error("리다이렉트 URL이 설정되지 않음")
                            raise Exception(
                                "인증이 필요하지만 리다이렉트 URL이 설정되지 않았습니다."
                            )

                    raise Exception(error_msg)

                result = self._parse_response(response)

                # 도구 호출인 경우 결과 로깅 (debug 레벨로 변경)
                if method == "tools/call" and params:
                    tool_name = params.get("name", "unknown")
                    ClientLogger.debug(
                        f"MCP 도구 호출 완료 - 도구: {tool_name}, SSO ID: {sso_id or 'None'}",
                        tool_name=tool_name,
                        result_type=type(result).__name__,
                        result_preview=str(result)[:200] if result else "None",
                        sso_id=sso_id,
                    )

                return result

            except Exception as e:
                error_str = str(e)
                ClientLogger.warning(
                    f"요청 시도 {attempt + 1} 실패", error=error_str, method=method
                )

                # UNAUTHORIZED 에러인 경우 재시도
                if "UNAUTHORIZED" in error_str and attempt < self.retry_attempts - 1:
                    ClientLogger.warning("인증 실패 감지, 재시도 중...")
                    # 헤더를 다시 생성
                    headers = self._get_headers(sso_id)
                    continue

                if attempt == self.retry_attempts - 1:
                    ClientLogger.error("모든 재시도 실패")
                    raise
                await asyncio.sleep(1 * (attempt + 1))

        raise Exception("모든 재시도 실패")

    def _create_server_info(self, result: Dict[str, Any]) -> MCPServerInfo:
        """서버 정보 객체 생성"""
        server_info = result.get("serverInfo", {})
        return MCPServerInfo(
            name=server_info.get("name", "Unknown"),
            version=server_info.get("version", "Unknown"),
            capabilities=result.get("capabilities", {}),
        )

    async def initialize(self) -> MCPServerInfo:
        """MCP 서버 초기화"""
        if self.initialized:
            ClientLogger.debug("이미 초기화됨, 기존 서버 정보 반환")
            return self.server_info

        try:
            ClientLogger.debug("MCP 서버 초기화 시작")
            result = await self._make_request("initialize")

            # 응답 내용 상세 로깅 (제거)

            self.server_info = self._create_server_info(result)
            self.initialized = True

            ClientLogger.debug(
                "MCP 서버 초기화 완료",
                server_name=self.server_info.name,
            )
            return self.server_info

        except Exception as e:
            ClientLogger.error("MCP 서버 초기화 실패", error=str(e))
            raise

    def _create_tool_from_data(self, tool_data: Dict[str, Any]) -> MCPTool:
        """도구 데이터에서 MCPTool 객체 생성"""
        return MCPTool(
            name=tool_data.get("name", ""),
            description=tool_data.get("description", ""),
            input_schema=tool_data.get("inputSchema", {}),
            output_schema=tool_data.get("outputSchema"),
        )

    async def list_tools(self) -> List[MCPTool]:
        """사용 가능한 도구 목록 조회"""
        if not self.initialized:
            await self.initialize()

        try:
            # ClientLogger.debug("도구 목록 조회 시작")
            result = await self._make_request("tools/list")
            tools_data = result.get("tools", [])

            self.available_tools = [
                self._create_tool_from_data(tool_data) for tool_data in tools_data
            ]

            # ClientLogger.debug(f"{len(self.available_tools)}개 도구 조회 완료")
            return self.available_tools

        except Exception as e:
            ClientLogger.error("도구 목록 조회 실패", error=str(e))
            self.available_tools = []
            return []

    def get_tool_names(self) -> List[str]:
        """사용 가능한 도구 이름 목록 반환 (scope용)"""
        return [tool.name for tool in self.available_tools]

    def _extract_tool_result(self, result: Dict[str, Any]) -> Any:
        """도구 실행 결과에서 실제 데이터 추출"""
        try:
            content = result.get("content", [])
            if content:
                first_content = content[0]
                extracted = (
                    first_content.get("text")
                    or first_content.get("data")
                    or first_content
                )

                # 문자열인 경우 JSON 파싱 시도
                if isinstance(extracted, str):
                    try:
                        import json

                        parsed = json.loads(extracted)
                        # 파싱된 결과가 오류인지 확인
                        if isinstance(parsed, dict) and "error_type" in parsed:
                            error_type = parsed.get("error_type")
                            error_message = parsed.get("message", "알 수 없는 오류")

                            if error_type == "INTERNAL_ERROR":
                                ClientLogger.error(
                                    "MCP 도구에서 내부 서버 오류 발생",
                                    tool_result=parsed,
                                    error_type=error_type,
                                    message=error_message,
                                )
                            else:
                                ClientLogger.warning(
                                    "MCP 도구에서 오류 응답 수신",
                                    tool_result=parsed,
                                    error_type=error_type,
                                    message=error_message,
                                )
                        return parsed
                    except (json.JSONDecodeError, TypeError):
                        # JSON 파싱 실패시 원본 문자열 반환
                        return extracted

                return extracted
            return result
        except Exception as e:
            ClientLogger.error("도구 결과 추출 중 오류", error=str(e), result=result)
            return result

    async def call_tool(
        self, tool_name: str, arguments: Dict[str, Any], sso_id: Optional[str] = None
    ) -> Any:
        """도구 실행"""
        if not self.initialized:
            await self.initialize()

        try:
            params = {"name": tool_name, "arguments": arguments}
            result = await self._make_request("tools/call", params, sso_id)

            if result["isError"]:
                error_info = json.loads(result["content"][0]["text"])

                # error_type에 따라 예외 처리
                if error_info["error_type"] in ["UNAUTHORIZED", "FORBIDDEN"]:
                    raise RAIHAuthorizationException(detail=error_info["message"])

                else:
                    raise RAIHBusinessException(detail=error_info["message"])

            extracted_result = self._extract_tool_result(result)

            return extracted_result

        except RAIHBusinessException as e:
            raise e

        except RAIHAuthorizationException as e:
            raise e
        except Exception as e:
            ClientLogger.error("도구 실행 실패", tool_name=tool_name, error=str(e))
            raise

    def get_tool_by_name(self, tool_name: str) -> Optional[MCPTool]:
        """이름으로 도구 찾기"""
        return next(
            (tool for tool in self.available_tools if tool.name == tool_name), None
        )

    def get_available_tool_names(self) -> List[str]:
        """사용 가능한 도구 이름 목록 반환"""
        return [tool.name for tool in self.available_tools]
