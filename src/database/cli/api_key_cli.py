"""
API Key 관리 CLI

API Key 발급, 조회, 비활성화 등을 위한 CLI 도구
"""

import sys
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.database.connection import get_database_session
from src.database.services.api_key_service import api_key_service


def create_api_key(name: Optional[str] = None, expires_in_days: Optional[int] = None):
    """API Key 생성"""
    db: Session = next(get_database_session())
    try:
        plain_key, api_key_obj = api_key_service.create_api_key(
            db=db, name=name, expires_in_days=expires_in_days
        )

        if not plain_key or not api_key_obj:
            print("❌ API Key 생성 실패")
            return

        print("✅ API Key 생성 완료")
        print(f"   ID: {api_key_obj.id}")
        print(f"   Name: {api_key_obj.name or '(이름 없음)'}")
        print(f"   Expires: {api_key_obj.expires_at or '만료 없음'}")
        print(f"\n⚠️  아래 키를 안전하게 보관하세요. 다시 확인할 수 없습니다!")
        print(f"\n{plain_key}\n")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        db.close()


def list_api_keys(include_inactive: bool = False):
    """API Key 목록 조회"""
    db: Session = next(get_database_session())
    try:
        keys = api_key_service.list_keys(db=db, include_inactive=include_inactive)

        if not keys:
            print("등록된 API Key가 없습니다.")
            return

        print(f"\n총 {len(keys)}개의 API Key:\n")
        print(f"{'ID':<6} {'Name':<20} {'Active':<8} {'Expires':<20} {'Last Used':<20}")
        print("-" * 80)

        for key in keys:
            active = "✅" if key.is_active else "❌"
            expires = (
                key.expires_at.strftime("%Y-%m-%d %H:%M:%S")
                if key.expires_at
                else "만료 없음"
            )
            last_used = (
                key.last_used_at.strftime("%Y-%m-%d %H:%M:%S")
                if key.last_used_at
                else "사용 안 함"
            )
            name = key.name or "(이름 없음)"

            print(f"{key.id:<6} {name:<20} {active:<8} {expires:<20} {last_used:<20}")

        print()

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        db.close()


def deactivate_api_key(key_id: int):
    """API Key 비활성화"""
    db: Session = next(get_database_session())
    try:
        success = api_key_service.deactivate_key(db=db, key_id=key_id)

        if success:
            print(f"✅ API Key (ID: {key_id}) 비활성화 완료")
        else:
            print(f"❌ API Key (ID: {key_id}) 비활성화 실패")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
    finally:
        db.close()


def main():
    """CLI 메인 함수"""
    if len(sys.argv) < 2:
        print("사용법:")
        print(
            "  python -m src.database.cli.api_key_cli create [name] [expires_in_days]"
        )
        print("  python -m src.database.cli.api_key_cli list [--include-inactive]")
        print("  python -m src.database.cli.api_key_cli deactivate <key_id>")
        sys.exit(1)

    command = sys.argv[1]

    if command == "create":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        expires_in_days = int(sys.argv[3]) if len(sys.argv) > 3 else None
        create_api_key(name=name, expires_in_days=expires_in_days)

    elif command == "list":
        include_inactive = "--include-inactive" in sys.argv
        list_api_keys(include_inactive=include_inactive)

    elif command == "deactivate":
        if len(sys.argv) < 3:
            print("❌ key_id를 입력해주세요")
            sys.exit(1)
        key_id = int(sys.argv[2])
        deactivate_api_key(key_id=key_id)

    else:
        print(f"❌ 알 수 없는 명령어: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
