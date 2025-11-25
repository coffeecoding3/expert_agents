# 프로젝트 설정 가이드

## 🚀 서버 초기 설정 (신규 서버)

새로운 서버에 처음 설정하는 경우 다음 순서로 진행하세요.

### 1단계: 패키지 매니저 설치

```bash
# uv 설치 (권장)
pip install uv

# 또는 pip만 사용하는 경우 이 단계 생략
```

### 2단계: 프로젝트 의존성 설치

```bash
# 프로젝트 디렉토리로 이동
cd /project/work/expert_agents

# 패키지 설치
python3 -m uv sync
# 또는 pip 사용: pip install -e .
```

### 3단계: 환경 변수 설정

#### 방법 A: 환경 변수로 설정

```bash
# 데이터베이스 연결 정보
export DATABASE_URL="mysql+pymysql://사용자명:비밀번호@호스트:포트/데이터베이스명?charset=utf8mb4"

# 예시
export DATABASE_URL="mysql+pymysql://dapadmin:password@10.182.177.212:3306/expert_agents?charset=utf8mb4"
```

#### 방법 B: configs/app.yaml 파일로 설정

```yaml
# configs/app.yaml
database:
  main:
    host: ${MYSQL_HOST:-10.182.177.212}
    port: ${MYSQL_PORT:-3306}
    user: ${MYSQL_USER:-dapadmin}
    password: "${MYSQL_PASSWORD:-password}"
    database: ${MYSQL_DATABASE:-expert_agents}
```

환경 변수 설정:
```bash
export MYSQL_HOST=10.182.177.212
export MYSQL_PORT=3306
export MYSQL_USER=dapadmin
export MYSQL_PASSWORD=password
export MYSQL_DATABASE=expert_agents
```

### 4단계: 데이터베이스 연결 확인

```bash
python3 -m uv run expert-agents db check
```

**성공 시**: "데이터베이스 연결이 정상입니다." 메시지 출력

### 5단계: 데이터베이스 생성

데이터베이스가 존재하지 않는 경우:

```bash
python3 -m uv run expert-agents db create-database
```

**참고**: 데이터베이스가 이미 존재하는 경우 이 단계는 건너뛰어도 됩니다.

### 6단계: 마이그레이션 적용 (테이블 생성)

```bash
python3 -m uv run expert-agents db upgrade
```

이 명령어는 모든 마이그레이션을 순차적으로 적용하여 필요한 테이블을 생성합니다.

### 7단계: 마이그레이션 상태 확인

```bash
# 현재 적용된 마이그레이션 확인
python3 -m uv run expert-agents db current

# 마이그레이션 히스토리 확인
python3 -m uv run expert-agents db history
```

### 8단계: 서버 실행

```bash
python main.py
```

---

## 📦 패키지 설치 (pyproject.toml 사용)

### 방법 1: uv 사용 (권장)

프로젝트에 `uv.lock` 파일이 있으므로 `uv`를 사용하는 것을 권장합니다.

#### uv 설치 방법

**방법 A: 공식 설치 스크립트 (네트워크 문제 시 실패할 수 있음)**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**방법 B: pip를 통한 설치 (네트워크 문제 시 대안)**
```bash
pip install uv
```

**방법 C: pipx를 통한 설치**
```bash
pipx install uv
```

**방법 D: 수동 다운로드 (curl 실패 시)**
```bash
# Linux/macOS
wget https://astral.sh/uv/install.sh
chmod +x install.sh
./install.sh

# 또는 직접 바이너리 다운로드
# https://github.com/astral-sh/uv/releases 에서 다운로드
```

#### 패키지 설치

```bash
# 패키지 설치
uv sync

# 또는 개발 의존성 포함
uv sync --dev
```

**참고**: 네트워크 문제로 curl이 실패하는 경우, `pip install uv`를 사용하거나 아래의 "방법 2: pip 사용"을 참고하세요.

### 방법 2: pip 사용

#### 개발 환경 (로컬 개발)

```bash
# 가상환경 생성 (개발 환경에서 권장)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 패키지 설치
pip install -e .

# 또는 개발 의존성 포함
pip install -e ".[dev]"
```

#### 운영 배포 환경

운영 환경에서는 이미 격리된 환경(Docker, 시스템 Python 등)이므로 가상환경 생성 없이 직접 설치:

```bash
# 가상환경 없이 직접 설치
pip install -e .

# 또는 특정 경로에 설치
pip install --prefix=/opt/expert-agents -e .

# 또는 시스템 Python에 설치 (권한 필요)
sudo pip install -e .
```

**참고**: 
- Docker 컨테이너를 사용하는 경우: 컨테이너 자체가 격리된 환경이므로 가상환경 불필요
- 시스템 Python 사용 시: `--user` 플래그로 사용자 디렉토리에 설치 가능
- 운영 환경에서는 개발 의존성(`[dev]`) 설치 불필요

## 🗄️ 데이터베이스 마이그레이션

### 1. 환경 변수 설정

데이터베이스 연결을 위해 환경 변수를 설정해야 합니다:

```bash
# .env 파일 생성 또는 환경 변수 설정
export DATABASE_URL="mysql+pymysql://user:password@localhost:3306/expert_agents?charset=utf8mb4"

# 또는 configs/app.yaml 파일에서 설정
```

### 2. 데이터베이스 연결 확인

```bash
# uv 사용
uv run expert-agents db check

# 또는 직접 실행
python -m src.database.cli.cli db check
```

### 3. 데이터베이스 생성 (데이터베이스가 없는 경우)

데이터베이스가 존재하지 않는 경우 먼저 생성해야 합니다:

```bash
# 데이터베이스 생성 (설정 파일의 database 값 사용)
python3 -m uv run expert-agents db create-database

# 또는 특정 데이터베이스 이름 지정
python3 -m uv run expert-agents db create-database --database my_database
```

### 4. 마이그레이션 실행

#### 초기 마이그레이션 (테이블 생성)

```bash
# 방법 1: Alembic을 통한 마이그레이션 (권장)
python3 -m uv run expert-agents db upgrade

# 방법 2: 직접 테이블 생성 (개발 환경용)
python3 -m uv run expert-agents db init
```

#### 새로운 마이그레이션 생성

모델을 변경한 후 새로운 마이그레이션을 생성:

```bash
uv run expert-agents db create-migration -m "마이그레이션 설명"
```

#### 마이그레이션 적용

```bash
# 최신 마이그레이션까지 적용
uv run expert-agents db upgrade

# 특정 revision까지 적용
uv run expert-agents db upgrade --revision <revision_id>
```

#### 마이그레이션 되돌리기

```bash
# 이전 마이그레이션으로 되돌리기
uv run expert-agents db downgrade

# 특정 revision으로 되돌리기
uv run expert-agents db downgrade --revision <revision_id>
```

#### 마이그레이션 상태 확인

```bash
# 현재 적용된 마이그레이션 확인
python3 -m uv run expert-agents db current

# 마이그레이션 히스토리 확인
python3 -m uv run expert-agents db history
```

#### 마이그레이션 버전 초기화 (문제 발생 시)

마이그레이션 버전이 맞지 않거나 오류가 발생하는 경우:

```bash
# 마이그레이션 버전을 init_schema.py (000000000000)로 초기화
python3 -m uv run expert-agents db reset-version

# 그 다음 마이그레이션 적용
python3 -m uv run expert-agents db upgrade
```

**주의**: 이 명령어는 데이터베이스의 `alembic_version` 테이블을 직접 수정합니다. 기존 데이터가 있는 경우 주의해서 사용하세요.

## 🚀 빠른 시작

### 신규 서버 초기 설정 체크리스트

- [ ] Python 3.11 이상 설치 확인
- [ ] uv 또는 pip 설치
- [ ] 프로젝트 의존성 설치 (`python3 -m uv sync` 또는 `pip install -e .`)
- [ ] 환경 변수 설정 (DATABASE_URL 또는 configs/app.yaml)
- [ ] 데이터베이스 연결 확인 (`db check`)
- [ ] 데이터베이스 생성 (`db create-database`)
- [ ] 마이그레이션 적용 (`db upgrade`)
- [ ] 서버 실행 테스트 (`python main.py`)

### 개발 환경 (로컬 개발)

```bash
# 1. 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. 패키지 설치
pip install -e ".[dev]"
# 또는 uv 사용: uv sync --dev

# 3. 환경 변수 설정
cp infra/compose/env.example .env
# .env 파일 편집

# 4. 데이터베이스 연결 확인
python -m src.database.cli.cli db check
# 또는 uv 사용: python3 -m uv run expert-agents db check

# 5. 데이터베이스 생성 (데이터베이스가 없는 경우)
python -m src.database.cli.cli db create-database
# 또는 uv 사용: python3 -m uv run expert-agents db create-database

# 6. 마이그레이션 적용
python -m src.database.cli.cli db upgrade
# 또는 uv 사용: python3 -m uv run expert-agents db upgrade

# 7. 서버 실행
python main.py
```

### 운영 배포 환경

```bash
# 1. 패키지 설치 (가상환경 없이)
pip install -e .
# 또는 uv 사용: python3 -m uv sync

# 2. 환경 변수 설정
# 환경 변수 또는 configs/app.yaml 설정
# 주의: 운영 환경에서는 보안을 위해 환경 변수 사용 권장

# 3. 데이터베이스 연결 확인
python3 -m src.database.cli.cli db check
# 또는 uv 사용: python3 -m uv run expert-agents db check

# 4. 데이터베이스 생성 (데이터베이스가 없는 경우)
python3 -m src.database.cli.cli db create-database
# 또는 uv 사용: python3 -m uv run expert-agents db create-database

# 5. 마이그레이션 적용
python3 -m src.database.cli.cli db upgrade
# 또는 uv 사용: python3 -m uv run expert-agents db upgrade

# 6. 서버 실행
python main.py
# 또는 systemd, supervisor 등으로 관리
```

**운영 환경 주의사항**:
- 가상환경 생성 불필요 (Docker 또는 시스템 Python 사용)
- 개발 의존성(`[dev]`) 설치 불필요
- 환경 변수는 보안을 위해 `.env` 파일보다 시스템 환경 변수 사용 권장
- 데이터베이스 백업 후 마이그레이션 실행 권장

## 📝 주요 명령어 요약

| 명령어 | 설명 |
|--------|------|
| `uv sync` | pyproject.toml의 모든 의존성 설치 |
| `python3 -m uv run expert-agents db check` | 데이터베이스 연결 확인 |
| `python3 -m uv run expert-agents db create-database` | 데이터베이스 생성 |
| `python3 -m uv run expert-agents db init` | 데이터베이스 초기화 (테이블 생성) |
| `python3 -m uv run expert-agents db upgrade` | 마이그레이션 적용 |
| `python3 -m uv run expert-agents db create-migration -m "설명"` | 새 마이그레이션 생성 |
| `python3 -m uv run expert-agents db current` | 현재 마이그레이션 상태 확인 |
| `python3 -m uv run expert-agents db history` | 마이그레이션 히스토리 확인 |
| `python3 -m uv run expert-agents db downgrade` | 마이그레이션 되돌리기 |
| `python3 -m uv run expert-agents db reset-version` | 마이그레이션 버전 초기화 (init_schema로) |
| `python3 -m uv run expert-agents db stamp --revision <revision>` | 마이그레이션 버전 수동 설정 |

## 🔧 문제 해결

### uv 설치 오류 (could not resolve host)

**문제**: `curl -LsSf https://astral.sh/uv/install.sh | sh` 실행 시 "could not resolve host" 오류 발생

**해결 방법**:

1. **pip를 통한 설치 (가장 간단한 대안)**
   ```bash
   pip install uv
   ```

2. **네트워크/DNS 확인**
   ```bash
   # DNS 확인
   nslookup astral.sh
   
   # 또는 ping 테스트
   ping astral.sh
   ```

3. **프록시 설정 확인** (회사 네트워크인 경우)
   ```bash
   # 프록시 설정이 필요한 경우
   export http_proxy=http://proxy.example.com:8080
   export https_proxy=http://proxy.example.com:8080
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

4. **uv 없이 pip 사용**
   - 아래 "방법 2: pip 사용" 섹션 참고
   - `uv.lock` 파일이 있어도 `pip install -e .`로 설치 가능

### 패키지 설치 오류

```bash
# uv 캐시 정리
uv cache clean

# 재설치
uv sync --reinstall

# pip 사용 시
pip install --upgrade -e .
```

### 마이그레이션 오류

#### "All MySQL CHANGE/MODIFY COLUMN operations require the existing type" 오류

**원인**: MySQL에서 컬럼 변경 시 기존 타입을 명시해야 함

**해결**: 마이그레이션 파일에서 `op.alter_column()` 사용 시 `existing_type` 파라미터 추가
```python
op.alter_column("table_name", "column_name", 
                existing_type=sa.Integer(),  # 기존 타입 명시
                nullable=False)
```

#### "Duplicate column name" 오류

**원인**: 마이그레이션이 부분적으로 실행되어 컬럼이 이미 존재

**해결**: 마이그레이션 파일에서 컬럼 존재 여부 확인 후 추가
```python
# 컬럼 존재 여부 확인
connection = op.get_bind()
inspector = sa.inspect(connection)
columns = [col['name'] for col in inspector.get_columns("table_name")]

if "column_name" not in columns:
    op.add_column("table_name", sa.Column("column_name", sa.Integer()))
```

#### "invalid interpolation syntax" 오류

**원인**: 데이터베이스 URL에 특수 문자(`!`, `$` 등)가 포함되어 configparser가 오류 발생

**해결**: 이미 `migrations/env.py`에서 수정됨. 직접 `get_database_url()` 사용

#### 마이그레이션 상태 확인 및 복구

```bash
# 마이그레이션 상태 확인
python3 -m uv run expert-agents db current

# 마이그레이션 히스토리 확인
python3 -m uv run expert-agents db history

# 특정 revision으로 되돌리기
python3 -m uv run expert-agents db downgrade --revision <revision_id>

# 특정 revision까지 적용
python3 -m uv run expert-agents db upgrade --revision <revision_id>
```

### 데이터베이스 연결 오류

#### "Unknown database" 오류

**원인**: 데이터베이스가 존재하지 않음

**해결**:
```bash
# 데이터베이스 생성
python3 -m uv run expert-agents db create-database
```

#### "The server is currently in offline mode" 오류

**원인**: MySQL 서버가 오프라인 모드로 설정됨

**해결**: MySQL 서버 관리자에게 오프라인 모드 해제 요청
```sql
-- MySQL 서버에서 실행
SET GLOBAL offline_mode = OFF;
```

#### 연결 실패 일반 해결 방법

1. **환경 변수 확인**
   ```bash
   echo $DATABASE_URL
   # 또는
   cat configs/app.yaml
   ```

2. **데이터베이스 서버 실행 확인**
   ```bash
   # MySQL 서버 연결 테스트
   mysql -h 호스트 -P 포트 -u 사용자명 -p
   ```

3. **연결 정보 확인**
   - 호스트: 올바른 IP 주소 또는 도메인
   - 포트: 기본값 3306
   - 사용자명: 데이터베이스 접근 권한이 있는 사용자
   - 비밀번호: 특수 문자 포함 시 URL 인코딩 필요
   - 데이터베이스명: 존재하는 데이터베이스 또는 생성 가능한 이름

4. **방화벽 확인**
   ```bash
   # 포트 접근 확인
   telnet 호스트 3306
   # 또는
   nc -zv 호스트 3306
   ```
