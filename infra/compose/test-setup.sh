#!/bin/bash

# Expert Agents Docker Test Setup Script

# 스크립트가 위치한 디렉토리로 이동하여 실행하도록 보장
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
cd "$SCRIPT_DIR" || exit

echo "🚀 Expert Agents Docker 환경 테스트 시작..."

# 환경 변수 파일 확인
if [ ! -f .env ]; then
    echo "📝 .env 파일이 없습니다. env.example을 복사합니다..."
    cp env.example .env
    echo "⚠️  .env 파일을 편집하여 API 키를 설정하세요!"
    echo "   특히 다음 항목들을 확인하세요:"
    echo "   - AZURE_OPENAI_KEY, AZURE_OPENAI_ENDPOINT"
    echo "   - GOOGLE_API_KEY, GOOGLE_CX"
    echo "   - SSO_KEY, NEXT_IAM_* 설정"
    echo "   - LGENIE_MCP_API_KEY, LGENIE_ENDPOINT"
fi

# Docker Compose 서비스 시작
echo "🐳 Docker Compose 서비스 시작 중... (코드 변경 자동 반영: APP_RELOAD=true)"
if ! docker-compose up -d --build; then
    echo "❌ Docker Compose 서비스 시작 실패!"
    echo "🔍 문제 해결을 위해 로그를 확인하세요: docker-compose logs"
    exit 1
fi

# 서비스 상태 확인
echo "📊 서비스 상태 확인 중..."
docker-compose ps

# 헬스체크 대기 (서비스 시작 시간 고려하여 대기 시간 증가)
echo "⏳ 서비스 헬스체크 대기 중... (최대 60초)"
for i in {1..12}; do
    echo "   대기 중... ($((i*5))초)"
    sleep 5
    
    # API 서비스가 실행 중인지 확인
    if docker-compose ps expert-agents | grep -q "Up"; then
        echo "✅ Expert Agents 서비스가 시작되었습니다."
        break
    fi
    
    if [ $i -eq 12 ]; then
        echo "⚠️  서비스 시작이 지연되고 있습니다. 계속 진행합니다..."
    fi
done

# API 헬스체크 (올바른 포트 사용)
echo "🏥 API 헬스체크 테스트..."
if curl -f http://localhost:8888/health 2>/dev/null; then
    echo "✅ API 서비스 헬스체크 성공"
else
    echo "❌ API 서비스가 아직 준비되지 않았습니다."
    echo "🔍 API 로그 확인: docker-compose logs expert-agents"
fi

# 데이터베이스 연결 테스트
echo "🗄️  MySQL 데이터베이스 연결 테스트..."
if docker-compose exec mysql mysql -u user -ppassword -e "SELECT 1;" 2>/dev/null; then
    echo "✅ MySQL 연결 성공"
else
    echo "❌ MySQL 연결 실패"
    echo "🔍 MySQL 로그 확인: docker-compose logs mysql"
fi

# DB 마이그레이션: memories.source 컬럼 추가 (없으면 생성)
echo "🛠️  DB 마이그레이션 실행 (memories.source 추가, 존재 시 무시)..."
if docker-compose exec mysql mysql -u root -prootpassword -e "ALTER TABLE expert_agents.memories ADD COLUMN IF NOT EXISTS source ENUM('fact','inferred') DEFAULT 'inferred' AFTER category;" 2>/dev/null; then
    echo "✅ 마이그레이션 완료 또는 이미 적용됨"
else
    echo "⚠️ 마이그레이션 실패 또는 이미 적용됨"
fi

# Redis 연결 테스트
echo "🔴 Redis 연결 테스트..."
if docker-compose exec redis redis-cli -a password ping 2>/dev/null | grep -q "PONG"; then
    echo "✅ Redis 연결 성공"
else
    echo "❌ Redis 연결 실패"
    echo "🔍 Redis 로그 확인: docker-compose logs redis"
fi

# 서비스별 상태 요약
echo ""
echo "📋 서비스 상태 요약:"
echo "===================="
docker-compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "🎯 테스트 완료!"
echo ""
echo "📱 접속 정보:"
echo "   - API: http://localhost:8888"
echo "   - API Health: http://localhost:8888/health"
echo "   - MySQL: localhost:3306 (user/password)"
echo "   - Redis: localhost:6379 (password: password)"
echo ""
echo "🔧 유용한 명령어:"
echo "   - 서비스 로그: docker-compose logs -f [service_name]"
echo "   - 서비스 중지: docker-compose down"
echo "   - 서비스 재시작: docker-compose up -d --no-deps --force-recreate expert-agents"
echo "   - 볼륨 정리: docker-compose down -v"
echo "   - 전체 재빌드: docker-compose up -d --build --force-recreate"
echo ""
echo "🐛 문제 해결:"
echo "   - 서비스가 시작되지 않으면: docker-compose logs [service_name]"
echo "   - 포트 충돌 시: netstat -tulpn | grep :8888"
echo "   - Docker 리소스 정리: docker system prune"
