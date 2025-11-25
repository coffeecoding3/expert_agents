# Expert Agents Docker 환경

이 디렉토리는 Expert Agents 서비스를 Docker 환경에서 실행하기 위한 설정 파일들을 포함합니다.

## 🚀 빠른 시작

### 1. 환경 설정
```bash
# 환경 변수 파일 설정
cp env.example .env
# .env 파일을 편집하여 API 키 설정
```

### 2. 서비스 시작
```bash
# 테스트 스크립트 실행 (권장)
./test-setup.sh

# 또는 수동으로 실행
docker-compose up -d
```

### 3. 서비스 확인
```bash
# 서비스 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs -f expert-agents
```

## 🏗️ 서비스 구성

### Core Services
- **expert-agents**: 메인 API 서비스 (포트 8000)
- **mysql**: MySQL 데이터베이스 (포트 3306)
- **redis**: Redis 캐시/세션 저장소 (포트 6379)

## 🔧 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 키 | - |
| `OPENAI_BASE_URL` | OpenAI/Azure API Base URL | - |
| `OPENAI_API_VERSION` | OpenAI API 버전 (Azure) | - |
| `GOOGLE_API_KEY` | Google AI API 키 | - |
| `EXAONE_API_KEY` | ExaOne API 키 | - |
| `APP_ENV` | 애플리케이션 환경 | development |
| `LOG_LEVEL` | 로그 레벨 | DEBUG |
| `ENABLE_METRICS` | 메트릭 활성화 | true |
| `ENABLE_TRACING` | 추적 활성화 | true |

## 📊 모니터링

### Grafana 대시보드
- URL: http://localhost:3000
- 계정: admin / admin
- Prometheus 데이터소스가 자동으로 설정됩니다

### Prometheus
- URL: http://localhost:9090
- Expert Agents 메트릭을 수집합니다

### Jaeger
- URL: http://localhost:16686
- 분산 추적 데이터를 시각화합니다

## 🗄️ 데이터베이스

### MySQL
- 데이터베이스: `expert_agents`
- 사용자: `user` / `password`
- 루트: `root` / `rootpassword`
- 관리자(시드): `caia-admin` / `!zkdldk123#$`

### Redis
- 비밀번호: `password`
- 지속성: AOF 활성화

### MongoDB
- 데이터베이스: `expert_agents`
- 루트: `admin` / `adminpassword`

## 🧪 테스트

### API 헬스체크
```bash
curl http://localhost:8000/health
```

### Azure OpenAI (사내 DNS 필요 시)

```yaml
extra_hosts:
  - "lgedap-azure-openai.openai.azure.com:10.182.173.71"
```

### 데이터베이스 연결 테스트
```bash
# MySQL
docker-compose exec mysql mysql -u user -ppassword -e "SELECT 1;"

# Redis
docker-compose exec redis redis-cli -a password ping

# MongoDB
docker-compose exec mongo mongosh --eval "db.adminCommand('ping')"
```

## 🛠️ 유용한 명령어

```bash
# 서비스 시작
docker-compose up -d

# 서비스 중지
docker-compose down

# 서비스 재시작
docker-compose restart [service_name]

# 로그 확인
docker-compose logs -f [service_name]

# 볼륨 정리 (데이터 삭제)
docker-compose down -v

# 특정 서비스만 재빌드
docker-compose build [service_name]

# 서비스 상태 확인
docker-compose ps
```

## 🔍 문제 해결

### 서비스가 시작되지 않는 경우
1. 로그 확인: `docker-compose logs [service_name]`
2. 포트 충돌 확인: `netstat -tulpn | grep :[PORT]`
3. Docker 리소스 확인: `docker system df`

### 데이터베이스 연결 실패
1. 서비스 헬스체크 확인: `docker-compose ps`
2. 네트워크 연결 확인: `docker network ls`
3. 환경 변수 확인: `.env` 파일

### 메모리 부족
1. Docker 리소스 제한 확인
2. 불필요한 컨테이너 정리: `docker system prune`
3. 볼륨 정리: `docker volume prune`

## 📝 개발 팁

- 소스 코드 변경 시 볼륨 마운트로 실시간 반영
- `docker-compose.override.yml`로 개발 환경 커스터마이징 가능
- 환경별 설정은 `docker-compose.{env}.yml`로 관리
