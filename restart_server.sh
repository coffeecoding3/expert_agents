#!/bin/bash

# Expert Agents 서버 재시작 스크립트
# 사용법: ./restart_server.sh [api|front|all|status|logs|stop|caia|raih|lexai]

set -e

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 프로젝트 루트 디렉토리로 이동
cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

# 환경변수 설정
export PYTHONPATH="$PROJECT_ROOT"
export ENV_FILE_PATH="$PROJECT_ROOT/infra/compose/.env"
export LOG_DIR="/tmp/logs"
export PROJECT_ROOT="$PROJECT_ROOT"

# 로그 디렉토리 생성
LOGS_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOGS_DIR"

# 기존 server.log를 날짜별로 이동하는 함수
rotate_existing_log() {
    if [ -f "$PROJECT_ROOT/server.log" ]; then
        local date_str=$(date +"%Y-%m-%d")
        local date_dir="$LOGS_DIR/$date_str"
        mkdir -p "$date_dir"
        
        local timestamp=$(date +"%Y%m%d_%H%M%S")
        local new_filename="$date_dir/server_${timestamp}.log"
        
        log_info "기존 server.log를 날짜별 디렉토리로 이동: $new_filename"
        mv "$PROJECT_ROOT/server.log" "$new_filename"
    fi
}

# 서버 중지 함수
stop_server() {
    local server_name=$1
    local process_pattern=$2
    
    log_info "$server_name 서버 중지 중..."
    
    if pgrep -f "$process_pattern" > /dev/null; then
        pkill -f "$process_pattern"
        sleep 2
        
        # 강제 종료 확인
        if pgrep -f "$process_pattern" > /dev/null; then
            log_warning "$server_name 서버가 정상 종료되지 않아 강제 종료합니다..."
            pkill -9 -f "$process_pattern"
            sleep 1
        fi
        
        log_success "$server_name 서버가 중지되었습니다."
    else
        log_info "$server_name 서버가 실행 중이 아닙니다."
    fi
}

# API 서버 시작 함수
start_api_server() {
    local agent_code=$1
    log_info "API 서버 시작 중..."
    
    # 기존 로그 파일을 날짜별로 이동
    rotate_existing_log
    
    # 에이전트 코드가 제공되면 환경변수로 설정 (소문자로 변환)
    if [ -n "$agent_code" ]; then
        local agent_code_lower=$(echo "$agent_code" | tr '[:upper:]' '[:lower:]')
        log_info "단일 에이전트 모드: $agent_code_lower"
        export ACTIVE_AGENT_CODE="$agent_code_lower"
    fi
    
    # Python 로깅이 server.log에 직접 쓰도록 설정되어 있으므로
    # stdout/stderr도 server.log로 리다이렉트 (uvicorn 기본 로그 포함)
    # 콘솔 핸들러 비활성화하여 중복 로그 방지
    ENABLE_CONSOLE_LOGGING=false nohup python3 -m src.apps.api.main >> server.log 2>&1 &
    local api_pid=$!
    
    sleep 5
    
    # 서버 상태 확인
    if ps -p $api_pid > /dev/null; then
        log_success "API 서버가 시작되었습니다. (PID: $api_pid)"
        log_info "API 서버 URL: http://localhost:8000"
        log_info "API 문서: http://localhost:8000/docs"
        log_info "로그 파일: $PROJECT_ROOT/server.log"
        log_info "로그 보관 디렉토리: $LOGS_DIR"
    else
        log_error "API 서버 시작에 실패했습니다."
        log_info "로그 확인: tail -f server.log"
        return 1
    fi
}

# 프론트엔드 서버 시작 함수
start_frontend_server() {
    log_info "프론트엔드 서버 시작 중..."
    
    nohup python3 serve_test.py > serve_test.log 2>&1 &
    local frontend_pid=$!
    
    sleep 3
    
    # 서버 상태 확인
    if ps -p $frontend_pid > /dev/null; then
        log_success "프론트엔드 서버가 시작되었습니다. (PID: $frontend_pid)"
        log_info "프론트엔드 서버 URL: http://localhost:9101/chat_test.html"
    else
        log_error "프론트엔드 서버 시작에 실패했습니다."
        log_info "로그 확인: tail -f serve_test.log"
        return 1
    fi
}

# 서버 상태 확인 함수
check_server_status() {
    log_info "서버 상태 확인 중..."
    
    # API 서버 상태
    if pgrep -f "src.apps.api.main" > /dev/null; then
        local api_pid=$(pgrep -f "src.apps.api.main")
        log_success "API 서버 실행 중 (PID: $api_pid)"
        
        # 헬스체크
        if curl -f http://localhost:8000/health > /dev/null 2>&1; then
            log_success "API 서버 헬스체크 통과"
        else
            log_warning "API 서버 헬스체크 실패"
        fi
    else
        log_warning "API 서버가 실행 중이 아닙니다."
    fi
    
    # 프론트엔드 서버 상태
    if pgrep -f "serve_test.py" > /dev/null; then
        local frontend_pid=$(pgrep -f "serve_test.py")
        log_success "프론트엔드 서버 실행 중 (PID: $frontend_pid)"
    else
        log_warning "프론트엔드 서버가 실행 중이 아닙니다."
    fi
}

# 로그 확인 함수
show_logs() {
    local server_type=$1
    
    case $server_type in
        "api")
            log_info "API 서버 로그 (최근 20줄):"
            if [ -f "$PROJECT_ROOT/server.log" ]; then
                tail -20 "$PROJECT_ROOT/server.log"
            else
                log_warning "server.log 파일이 없습니다."
            fi
            ;;
        "front")
            log_info "프론트엔드 서버 로그 (최근 20줄):"
            tail -20 serve_test.log
            ;;
        *)
            log_info "API 서버 로그 (최근 10줄):"
            if [ -f "$PROJECT_ROOT/server.log" ]; then
                tail -10 "$PROJECT_ROOT/server.log"
            else
                log_warning "server.log 파일이 없습니다."
            fi
            echo ""
            log_info "프론트엔드 서버 로그 (최근 10줄):"
            tail -10 serve_test.log
            ;;
    esac
}

# 메인 로직
main() {
    local action=${1:-"all"}
    
    echo "=========================================="
    echo "🚀 Expert Agents 서버 재시작 스크립트"
    echo "=========================================="
    
    # 입력값을 소문자로 변환 (대소문자 구분 없이 처리)
    local action_lower=$(echo "$action" | tr '[:upper:]' '[:lower:]')
    
    # 에이전트 코드인지 확인 (caia, raih, lexai 등)
    local valid_agent_codes=("caia" "raih" "lexai")
    local is_agent_code=false
    
    for code in "${valid_agent_codes[@]}"; do
        if [ "$action_lower" == "$code" ]; then
            is_agent_code=true
            break
        fi
    done
    
    # 에이전트 코드인 경우 단일 에이전트 모드로 실행
    if [ "$is_agent_code" == true ]; then
        log_info "단일 에이전트 모드로 실행: $action_lower"
        stop_server "API" "src.apps.api.main"
        start_api_server "$action_lower"
        return 0
    fi
    
    # 기존 옵션도 소문자로 변환된 값으로 처리
    action="$action_lower"
    
    # 기존 옵션 처리
    case $action in
        "api")
            stop_server "API" "src.apps.api.main"
            start_api_server
            ;;
        "front")
            stop_server "프론트엔드" "serve_test.py"
            start_frontend_server
            ;;
        "all")
            stop_server "API" "src.apps.api.main"
            stop_server "프론트엔드" "serve_test.py"
            start_api_server
            start_frontend_server
            ;;
        "status")
            check_server_status
            ;;
        "logs")
            show_logs ${2:-"all"}
            ;;
        "stop")
            stop_server "API" "src.apps.api.main"
            stop_server "프론트엔드" "serve_test.py"
            log_success "모든 서버가 중지되었습니다."
            ;;
        *)
            echo "사용법: $0 [api|front|all|status|logs|stop|caia|raih|lexai]"
            echo ""
            echo "옵션:"
            echo "  api     - API 서버만 재시작"
            echo "  front   - 프론트엔드 서버만 재시작"
            echo "  all     - 모든 서버 재시작 (기본값)"
            echo "  status  - 서버 상태 확인"
            echo "  logs    - 서버 로그 확인"
            echo "  stop    - 모든 서버 중지"
            echo ""
            echo "단일 에이전트 모드:"
            echo "  caia    - CAIA 에이전트만 등록하여 서버 시작"
            echo "  raih    - RAIH 에이전트만 등록하여 서버 시작"
            echo "  lexai   - LexAI 에이전트만 등록하여 서버 시작"
            echo ""
            echo "예시:"
            echo "  $0              # 모든 서버 재시작"
            echo "  $0 api          # API 서버만 재시작"
            echo "  $0 caia         # CAIA 에이전트만 등록하여 시작"
            echo "  $0 status       # 서버 상태 확인"
            echo "  $0 logs api     # API 서버 로그 확인"
            exit 1
            ;;
    esac
    
    echo ""
    log_info "완료! 서버 관리 명령어:"
    echo "  상태 확인: $0 status"
    echo "  로그 확인: $0 logs"
    echo "  서버 중지: $0 stop"
}

# 스크립트 실행
main "$@"
