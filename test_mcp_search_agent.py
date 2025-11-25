#!/usr/bin/env python3
"""
MCP Search Agent 연결 테스트 스크립트
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.agents.search_agent import SearchAgentWrapper
from src.llm.manager import llm_manager
from configs.app_config import load_config

# 로깅 설정
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def test_mcp_connection():
    """MCP 서버 연결 테스트"""
    logger.info("=== MCP Search Agent 연결 테스트 시작 ===")

    try:
        # Config 로드 및 LLM Manager 초기화
        config = load_config()
        await llm_manager.initialize(config)

        # SearchAgent 인스턴스 생성 (agent_code 필요)
        # 데이터베이스에 등록된 agent_code 사용 (예: "caia", "raih", "search_agent")
        # 기본값으로 "caia" 사용
        agent_code = config.get("test_agent_code", "caia")
        search_agent = SearchAgentWrapper(config={"agent_code": agent_code})

        # MCP 연결 테스트 실행
        test_result = await search_agent.test_mcp_connection()

        # 결과 출력
        print("\n" + "=" * 60)
        print("MCP 연결 테스트 결과")
        print("=" * 60)
        print(json.dumps(test_result, indent=2, ensure_ascii=False))

        # 요약 출력
        print("\n" + "-" * 60)
        print("테스트 요약:")
        print(f"- 테스트명: {test_result.get('test_name', 'N/A')}")
        print(f"- 전체 상태: {test_result.get('overall_status', 'N/A')}")
        print(f"- 요약: {test_result.get('summary', 'N/A')}")

        # 단계별 결과
        if "steps" in test_result:
            print(f"\n단계별 결과:")
            for step in test_result["steps"]:
                status_emoji = (
                    "✅"
                    if step["status"] == "success"
                    else "❌" if step["status"] == "failed" else "⏭️"
                )
                print(
                    f"  {status_emoji} Step {step['step']}: {step['name']} - {step['message']}"
                )

        # MCP 연결 정보
        if "mcp_connection" in test_result:
            mcp_info = test_result["mcp_connection"]
            print(f"\nMCP 연결 정보:")
            print(
                f"  - 연결 상태: {'연결됨' if mcp_info['connected'] else '연결 실패'}"
            )
            print(f"  - 사용 가능한 도구 수: {mcp_info['tools_count']}")
            print(f"  - 메시지: {mcp_info['message']}")

            if mcp_info["tools"]:
                print(f"\n사용 가능한 MCP 도구:")
                for tool in mcp_info["tools"]:
                    print(
                        f"  - {tool.get('name', 'N/A')}: {tool.get('description', 'N/A')}"
                    )

        return test_result.get("overall_status") == "success"

    except Exception as e:
        logger.error(f"테스트 실행 중 오류 발생: {e}")
        print(f"\n❌ 테스트 실행 실패: {e}")
        return False


async def test_search_with_mcp():
    """MCP 도구를 포함한 검색 테스트"""
    logger.info("=== MCP 도구를 포함한 검색 테스트 시작 ===")

    try:
        # LLM Manager 초기화 (이미 초기화되었을 수 있음)
        if not llm_manager.is_initialized:
            config = load_config()
            await llm_manager.initialize(config)

        # SearchAgent 인스턴스 생성 (agent_code 필요)
        # 데이터베이스에 등록된 agent_code 사용
        config_obj = load_config()
        agent_code = config_obj.get("test_agent_code", "caia")
        search_agent = SearchAgentWrapper(config={"agent_code": agent_code})

        # 테스트 쿼리
        test_query = "오늘 날씨는 어떤가요?"
        user_context = {"sso_id": "test_user", "intent": "search"}

        print(f"\n테스트 쿼리: {test_query}")
        print("검색 실행 중...")

        # 검색 실행 (스트리밍 없이)
        result = await search_agent._run_search_logic(
            query=test_query, user_context=user_context
        )

        # 결과 출력
        print("\n" + "=" * 60)
        print("검색 결과")
        print("=" * 60)
        print(f"계획: {len(result.get('plan', []))}개 단계")
        print(f"도구 실행 결과: {len(result.get('tool_results', []))}개")
        print(f"요약 길이: {len(str(result.get('summary', '')))} 문자")

        # 도구 실행 결과 상세
        if result.get("tool_results"):
            print(f"\n도구 실행 결과:")
            for i, tool_result in enumerate(result["tool_results"]):
                provider = tool_result.get("provider", "basic")
                client = tool_result.get("client", "N/A")
                print(f"  {i+1}. {tool_result.get('tool', 'N/A')} ({provider})")
                if provider == "mcp":
                    print(f"     - 클라이언트: {client}")
                print(f"     - 실행 시간: {tool_result.get('duration', 0):.3f}초")
                print(
                    f"     - 결과 길이: {len(str(tool_result.get('result', '')))} 문자"
                )

        return True

    except Exception as e:
        logger.error(f"검색 테스트 실행 중 오류 발생: {e}")
        print(f"\n❌ 검색 테스트 실행 실패: {e}")
        return False


async def main():
    """메인 테스트 함수"""
    print("MCP Search Agent 테스트 시작")
    print("=" * 60)

    # 1. MCP 연결 테스트
    connection_success = await test_mcp_connection()

    if connection_success:
        print("\n✅ MCP 연결 테스트 성공!")

        # 2. MCP 도구를 포함한 검색 테스트
        search_success = await test_search_with_mcp()

        if search_success:
            print("\n✅ 검색 테스트 성공!")
        else:
            print("\n❌ 검색 테스트 실패!")
    else:
        print("\n❌ MCP 연결 테스트 실패!")
        print("MCP 서버 설정을 확인해주세요.")

    print("\n" + "=" * 60)
    print("테스트 완료")


if __name__ == "__main__":
    asyncio.run(main())
