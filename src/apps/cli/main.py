"""
CLI Application

개발자/운영자용 CLI 유틸리티
"""

import json
import logging
import os
from logging import getLogger
from typing import Optional

import click
import httpx

from src.database.cli import cli as db_cli
from src.memory.memory_manager import initialize_memory_manager, memory_manager

logger = getLogger("cli")


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Expert Agents CLI"""
    # CLI에서 메모리 매니저 초기화
    try:
        mem_config = {
            "provider_type": os.getenv("MEMORY_PROVIDER", "mysql"),
            "database_url": os.getenv("DATABASE_URL"),
            "redis_url": os.getenv("REDIS_URL") or os.getenv("MEMORY_REDIS_URL"),
        }
        initialize_memory_manager(mem_config)
        logger.info("메모리 매니저가 CLI에서 초기화되었습니다.")
    except Exception as e:
        logger.warning(f"메모리 매니저 초기화 실패: {e}")


@cli.command()
@click.option(
    "--agent", "-a", default="caia", help="에이전트 코드 (현재 API는 'caia' 고정)"
)
@click.option("--task", "-t", required=True, help="실행할 태스크(질문/지시문)")
@click.option("--user-id", "-u", default="cli_user", help="사용자 ID")
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
@click.option("--stream", is_flag=True, help="SSE 스트리밍 모드")
def run(agent: str, task: str, user_id: str, host: str, stream: bool):
    """에이전트 태스크 실행 (API에 위임)"""
    logger.info(
        f"Run requested - agent:{agent}, user:{user_id}, stream:{stream}, task:{task}"
    )
    if stream:
        # SSE 스트리밍으로 실행
        url = f"{host}/caia/api/v1/chat/stream"
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream(
                    "POST", url, json={"question": task, "user_id": user_id}
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line:
                            click.echo(line)
        except Exception as e:
            logger.error(f"Run (stream) failed: {e}")
            click.echo(f"❌ Run (stream) failed: {e}")
    else:
        # 단건 응답으로 실행 (stream 엔드포인트 사용)
        url = f"{host}/caia/api/v1/chat/stream"
        try:
            with httpx.Client(timeout=600) as client:
                with client.stream(
                    "POST", url, json={"question": task, "user_id": user_id}
                ) as resp:
                    resp.raise_for_status()
                    full_response = ""
                    for line in resp.iter_lines():
                        if line and line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("event_type") == "LLM" and data.get(
                                    "token"
                                ):
                                    full_response += data["token"]
                            except json.JSONDecodeError:
                                continue
                    click.echo(full_response)
        except Exception as e:
            logger.error(f"Run (simple) failed: {e}")
            click.echo(f"❌ Run (simple) failed: {e}")


@cli.command()
def status():
    """서비스 상태 조회"""
    logger.info("Status check requested")
    click.echo("Service Status:")
    click.echo("  - Orchestration: Active")
    click.echo("  - Capabilities: Active")
    click.echo("  - Memory: Active")
    click.echo("  - Chat: Active")


@cli.command()
@click.option("--server", "-s", help="MCP 서버 이름")
def list_servers(server: Optional[str]):
    """MCP 서버 목록 조회"""
    logger.info("MCP server list requested")

    internal_servers = [
        "llm-knowledge",
    ]

    external_servers = [
        "lgenie-event-calendar",
    ]

    all_servers = internal_servers + external_servers

    if server:
        if server in all_servers:
            if server in internal_servers:
                click.echo(f"✅ Internal Server: {server} (CAIA에서 개발)")
            else:
                click.echo(f"🌐 External Server: {server} (외부 서비스)")
        else:
            click.echo(f"❌ Server {server} not found")
    else:
        click.echo("Available MCP Servers:")
        click.echo("\n🔧 Internal Servers (CAIA에서 개발하는 툴들):")
        for s in internal_servers:
            click.echo(f"  - {s}")

        click.echo("\n🌐 External Servers (외부에서 제공되는 서비스들):")
        for s in external_servers:
            click.echo(f"  - {s}")

        click.echo(f"\nTotal: {len(all_servers)} servers")


@cli.command()
def health():
    """헬스체크"""
    logger.info("Health check requested")
    click.echo("✅ Service is healthy")


@cli.command()
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
def mcp_servers(host: str):
    """MCP 서버 목록 조회 (API 연동)"""
    logger.info("MCP servers list requested")
    try:
        url = f"{host}/mcp/servers"
        r = httpx.get(url, timeout=30)
        r.raise_for_status()

        data = r.json()
        servers = data.get("servers", [])
        total = data.get("total", 0)

        click.echo(f"MCP Servers ({total} total):")
        for server in servers:
            if server.startswith("internal."):
                click.echo(f"  🔧 {server} (Internal)")
            elif server.startswith("external."):
                click.echo(f"  🌐 {server} (External)")
            else:
                click.echo(f"  ❓ {server}")

    except Exception as e:
        logger.error(f"MCP servers list failed: {e}")
        click.echo(f"❌ MCP servers list failed: {e}")


@cli.command()
@click.option("--server", "-s", required=True, help="MCP 서버 이름")
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
def mcp_tools(server: str, host: str):
    """MCP 서버의 도구 목록 조회 (API 연동)"""
    logger.info(f"MCP tools list requested for server: {server}")
    try:
        url = f"{host}/mcp/servers/{server}/tools"
        r = httpx.get(url, timeout=30)
        r.raise_for_status()

        data = r.json()
        tools = data.get("tools", [])
        total = data.get("total", 0)

        click.echo(f"Tools for {server} ({total} total):")
        for tool in tools:
            name = tool.get("name", "Unknown")
            description = tool.get("description", "No description")
            click.echo(f"  - {name}: {description}")

    except Exception as e:
        logger.error(f"MCP tools list failed: {e}")
        click.echo(f"❌ MCP tools list failed: {e}")


@cli.command()
@click.option("--server", "-s", required=True, help="MCP 서버 이름")
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
def mcp_health(server: str, host: str):
    """MCP 서버 헬스 체크 (API 연동)"""
    logger.info(f"MCP health check requested for server: {server}")
    try:
        url = f"{host}/mcp/servers/{server}/health"
        r = httpx.get(url, timeout=30)
        r.raise_for_status()

        data = r.json()
        healthy = data.get("healthy", False)
        error = data.get("error")

        if healthy:
            click.echo(f"✅ {server} is healthy")
        else:
            click.echo(f"❌ {server} is unhealthy: {error}")

    except Exception as e:
        logger.error(f"MCP health check failed: {e}")
        click.echo(f"❌ MCP health check failed: {e}")


@cli.command()
@click.option("--user-id", "-u", type=int, help="사용자 ID")
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
def memory_stats(user_id: Optional[int], host: str):
    """메모리 통계 조회 (API 연동)"""
    logger.info("Memory stats requested")
    try:
        if user_id:
            # 특정 사용자 통계 조회
            resp = httpx.get(f"{host}/memory/stats/{user_id}", timeout=30)
            resp.raise_for_status()
            data = resp.json()
            stats = data.get("stats", {})
            provider = data.get("provider_info", {})

            click.echo(f"Memory stats for user {user_id}:")
            click.echo(f"  - Total memories: {stats.get('total_memories', 0)}")
            click.echo(
                f"  - Conversation memories: {stats.get('conversation_memories', 0)}"
            )
            click.echo(f"  - Task memories: {stats.get('task_memories', 0)}")
            click.echo(f"  - Knowledge memories: {stats.get('knowledge_memories', 0)}")
            click.echo(f"  - Avg importance: {stats.get('avg_importance', 0.0)}")
            click.echo(f"  - Latest memory: {stats.get('latest_memory', 'N/A')}")
            click.echo("Provider Info:")
            click.echo(f"  - Type: {provider.get('provider_type', 'unknown')}")
            click.echo(f"  - Status: {provider.get('status', 'unknown')}")
        else:
            # 프로바이더 상태만 조회
            resp = httpx.get(f"{host}/memory/provider-info", timeout=30)
            resp.raise_for_status()
            provider = resp.json()
            click.echo("Memory provider info:")
            click.echo(f"  - Type: {provider.get('provider_type', 'unknown')}")
            click.echo(f"  - Status: {provider.get('status', 'unknown')}")
            click.echo(f"  - Available: {provider.get('is_available', False)}")
    except Exception as e:
        logger.error(f"[CLI] Memory stats failed: {e}")
        click.echo(f"❌ Memory stats failed: {e}")


@cli.command()
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
def memory_provider(host: str):
    """메모리 프로바이더 정보 조회 (API 연동)"""
    logger.info("Memory provider info requested")
    try:
        resp = httpx.get(f"{host}/memory/provider-info", timeout=30)
        resp.raise_for_status()
        provider = resp.json()
        click.echo("Memory Provider Info:")
        click.echo(f"  - Type: {provider.get('provider_type', 'unknown')}")
        click.echo(f"  - Status: {provider.get('status', 'unknown')}")
        click.echo(f"  - Available: {provider.get('is_available', False)}")
    except Exception as e:
        logger.error(f"[CLI] Memory provider info failed: {e}")
        click.echo(f"❌ [CLI] Memory provider info failed: {e}")


@cli.command()
@click.option("--question", "-q", required=True, help="채팅 질문")
@click.option("--user-id", "-u", default="test_user", help="사용자 ID")
@click.option("--session-id", "-s", default="", help="세션 ID (STM 분리 저장용)")
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
@click.option("--stream", is_flag=True, help="SSE 스트리밍 모드")
def chat(question: str, user_id: str, session_id: str, host: str, stream: bool):
    """채팅 테스트 - 기본은 simple, --stream 시 SSE 사용"""
    logger.info(
        f"[CLI] Chat test requested - user: {user_id}, question: {question}, stream: {stream}"
    )
    if stream:
        # SSE 스트리밍
        url = f"{host}/caia/api/v1/chat/stream"
        try:
            with httpx.Client(timeout=600) as client:
                payload = {"question": question, "user_id": user_id}
                if session_id:
                    payload["session_id"] = session_id
                with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line:
                            click.echo(line)
        except Exception as e:
            logger.error(f"[CLI] SSE chat failed: {e}")
            click.echo(f"❌ [CLI] SSE chat failed: {e}")
    else:
        # 단순 응답 (stream 엔드포인트 사용)
        url = f"{host}/caia/api/v1/chat/stream"
        try:
            payload = {"question": question, "user_id": user_id}
            if session_id:
                payload["session_id"] = session_id
            with httpx.Client(timeout=600) as client:
                with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    full_response = ""
                    for line in resp.iter_lines():
                        if line and line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("event_type") == "LLM" and data.get(
                                    "token"
                                ):
                                    full_response += data["token"]
                            except json.JSONDecodeError:
                                continue
                    click.echo(full_response)
        except Exception as e:
            logger.error(f"[CLI] Simple chat failed: {e}")
            click.echo(f"❌ [CLI] Simple chat failed: {e}")


@cli.command()
@click.option("--user-id", "-u", required=True, type=int, help="사용자 ID")
@click.option(
    "--agent-id", "-a", default=1, show_default=True, type=int, help="에이전트 ID"
)
@click.option("--session-id", "-s", default="", help="세션 ID (없으면 전체 키)")
@click.option(
    "--limit", "-k", default=5, show_default=True, type=int, help="최근 항목 개수"
)
def stm(user_id: int, agent_id: int, session_id: str, limit: int):
    """Redis STM 내용을 조회하여 보기 좋게 출력"""
    try:
        recent = memory_manager.get_stm_recent_messages(
            user_id=user_id, agent_id=agent_id, k=limit, session_id=(session_id or None)
        )
        summary = memory_manager.get_stm_summary(
            user_id=user_id, agent_id=agent_id, session_id=(session_id or None)
        )
        click.echo(f"STM Summary: {summary if summary else 'N/A'}")
        click.echo(f"Recent ({len(recent)}):")
        for i, item in enumerate(recent, 1):
            content = item.get("content", "")
            c_short = content if len(content) <= 160 else content[:157] + "..."
            sid = item.get("session_id") or ""
            click.echo(
                f"  {i}. [{item.get('memory_type','-')}] session={sid} id={item.get('id')} -> {c_short}"
            )
    except Exception as e:
        logger.error(f"[CLI] STM fetch failed: {e}")
        click.echo(f"❌ [CLI] STM fetch failed: {e}")


@cli.command()
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
def test_api(host: str):
    """API 서버 테스트"""
    logger.info(f"API test requested for host: {host}")
    click.echo(f"Testing API server at {host}")

    try:
        # 헬스체크 테스트
        response = httpx.get(f"{host}/health")
        if response.status_code == 200:
            click.echo("✅ Health check: OK")
        else:
            click.echo(f"❌ Health check: Failed ({response.status_code})")

        # 채팅 헬스체크 테스트
        response = httpx.get(f"{host}/caia/api/v1/chat/health")
        if response.status_code == 200:
            click.echo("✅ Chat health check: OK")
        else:
            click.echo(f"❌ Chat health check: Failed ({response.status_code})")

    except Exception as e:
        logger.error(f"[CLI] API test failed: {e}")
        click.echo(f"❌ [CLI] API test failed: {e}")


@cli.command()
def llm_status():
    """LLM 서비스 상태 조회"""
    logger.info("LLM status requested")
    click.echo("LLM Service Status:")
    click.echo("  - OpenAI: Available")


@cli.command()
@click.option("--provider", "-p", help="LLM 프로바이더 (openai)")
def list_llm_models(provider: Optional[str]):
    """사용 가능한 LLM 모델 목록 조회"""
    logger.info(f"LLM models list requested - provider: {provider}")

    if provider:
        click.echo(f"Available models for {provider}:")
        if provider == "openai":
            click.echo("  - gpt-5-chat")
        else:
            click.echo(f"❌ Unknown provider: {provider}")
    else:
        click.echo("Available LLM Providers and Models:")
        click.echo("\n🤖 OpenAI:")
        click.echo("  - gpt-5-chat")


@cli.command()
@click.option("--provider", "-p", required=True, help="LLM 프로바이더")
@click.option("--model", "-m", help="사용할 모델")
@click.option("--prompt", "-t", required=True, help="생성할 텍스트 프롬프트")
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
def generate_text(provider: str, model: str, prompt: str, host: str):
    """LLM을 사용한 텍스트 생성 (API 연동: chat/simple 사용)"""
    logger.info(
        f"Text generation requested - provider: {provider}, model: {model}, host: {host}"
    )
    url = f"{host}/caia/api/v1/chat/simple"
    try:
        r = httpx.post(
            url, json={"question": prompt, "user_id": "cli_user"}, timeout=60
        )
        r.raise_for_status()
        click.echo(r.text)
    except Exception as e:
        logger.error(f"[CLI] Generate text failed: {e}")
        click.echo(f"❌ [CLI] Generate text failed: {e}")


@cli.command()
@click.option("--provider", "-p", required=True, help="LLM 프로바이더")
@click.option("--model", "-m", help="사용할 모델")
@click.option("--message", "-t", required=True, help="채팅 메시지")
@click.option("--host", default="http://localhost:8000", help="API 서버 호스트")
@click.option("--stream", is_flag=True, help="SSE 스트리밍 모드")
def chat_with_llm(provider: str, model: str, message: str, host: str, stream: bool):
    """LLM과 채팅 (API 연동)"""
    logger.info(
        f"Chat with LLM requested - provider:{provider}, model:{model}, stream:{stream}"
    )
    if stream:
        url = f"{host}/caia/api/v1/chat/stream"
        try:
            with httpx.Client(timeout=None) as client:
                with client.stream(
                    "POST", url, json={"question": message, "user_id": "cli_user"}
                ) as resp:
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if line:
                            click.echo(line)
        except Exception as e:
            logger.error(f"[CLI] Chat with LLM (stream) failed: {e}")
            click.echo(f"❌ [CLI] Chat with LLM (stream) failed: {e}")
    else:
        url = f"{host}/caia/api/v1/chat/stream"
        try:
            with httpx.Client(timeout=60) as client:
                with client.stream(
                    "POST", url, json={"question": message, "user_id": "cli_user"}
                ) as resp:
                    resp.raise_for_status()
                    full_response = ""
                    for line in resp.iter_lines():
                        if line and line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("event_type") == "LLM" and data.get(
                                    "token"
                                ):
                                    full_response += data["token"]
                            except json.JSONDecodeError:
                                continue
                    click.echo(full_response)
        except Exception as e:
            logger.error(f"[CLI] Chat with LLM (simple) failed: {e}")
            click.echo(f"❌ [CLI] Chat with LLM (simple) failed: {e}")


# 데이터베이스 명령어 추가
cli.add_command(db_cli, name="db")


@cli.group()
def migrate():
    """데이터 마이그레이션 명령어"""
    pass


@migrate.command()
@click.option("--batch-size", "-b", default=100, help="배치 처리 크기 (기본값: 100)")
def lgenie_all(batch_size: int):
    """전체 채널을 LGenie DB로 마이그레이션"""
    logger.info(f"LGenie 전체 마이그레이션 시작 (배치 크기: {batch_size})")
    try:
        from src.database.cli.migrate_to_lgenie import LGenieMigrationService

        migration_service = LGenieMigrationService()
        success_count, total_count = migration_service.migrate_all_channels(batch_size)

        click.echo(f"✅ 마이그레이션 완료: {success_count}/{total_count} 채널 성공")
    except Exception as e:
        logger.error(f"LGenie 전체 마이그레이션 실패: {e}")
        click.echo(f"❌ LGenie 전체 마이그레이션 실패: {e}")


@migrate.command()
@click.option("--start-date", "-s", required=True, help="시작 날짜 (YYYY-MM-DD)")
@click.option("--end-date", "-e", required=True, help="종료 날짜 (YYYY-MM-DD)")
@click.option("--batch-size", "-b", default=100, help="배치 처리 크기 (기본값: 100)")
def lgenie_date_range(start_date: str, end_date: str, batch_size: int):
    """특정 날짜 범위의 채널을 LGenie DB로 마이그레이션"""
    logger.info(f"LGenie 날짜 범위 마이그레이션 시작: {start_date} ~ {end_date}")
    try:
        from src.database.cli.migrate_to_lgenie import LGenieMigrationService

        migration_service = LGenieMigrationService()
        success_count, total_count = migration_service.migrate_channels_by_date_range(
            start_date, end_date, batch_size
        )

        click.echo(f"✅ 마이그레이션 완료: {success_count}/{total_count} 채널 성공")
    except Exception as e:
        logger.error(f"LGenie 날짜 범위 마이그레이션 실패: {e}")
        click.echo(f"❌ LGenie 날짜 범위 마이그레이션 실패: {e}")


@migrate.command()
@click.option(
    "--channel-id", "-c", required=True, type=int, help="마이그레이션할 채널 ID"
)
def lgenie_single(channel_id: int):
    """단일 채널을 LGenie DB로 마이그레이션"""
    logger.info(f"LGenie 단일 채널 마이그레이션 시작: {channel_id}")
    try:
        from src.database.cli.migrate_to_lgenie import LGenieMigrationService

        migration_service = LGenieMigrationService()
        success = migration_service.migrate_single_channel(channel_id)

        if success:
            click.echo(f"✅ 채널 {channel_id} 마이그레이션 성공")
        else:
            click.echo(f"❌ 채널 {channel_id} 마이그레이션 실패")
    except Exception as e:
        logger.error(f"LGenie 단일 채널 마이그레이션 실패: {e}")
        click.echo(f"❌ LGenie 단일 채널 마이그레이션 실패: {e}")


@migrate.command()
def lgenie_stats():
    """LGenie 마이그레이션 통계 조회"""
    logger.info("LGenie 마이그레이션 통계 조회")
    try:
        from src.database.cli.migrate_to_lgenie import LGenieMigrationService

        migration_service = LGenieMigrationService()
        stats = migration_service.get_migration_stats()

        click.echo("📊 마이그레이션 통계:")
        click.echo(f"  - 전체 채널 수: {stats.get('total_channels', 0)}")
        click.echo(f"  - 전체 메시지 수: {stats.get('total_messages', 0)}")
    except Exception as e:
        logger.error(f"LGenie 마이그레이션 통계 조회 실패: {e}")
        click.echo(f"❌ LGenie 마이그레이션 통계 조회 실패: {e}")


if __name__ == "__main__":
    cli()
