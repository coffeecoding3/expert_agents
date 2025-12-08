"""
LGenie DB 마이그레이션 스크립트

Main DB의 기존 채팅 데이터를 LGenie DB로 일괄 복사하는 스크립트
"""

import argparse
from logging import getLogger
from typing import List, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models.chat import ChatChannel, ChatMessage
from src.database.services.lgenie_sync_service import LGenieSyncService

logger = getLogger("migration")


class LGenieMigrationService:
    """LGenie DB 마이그레이션 서비스"""

    def __init__(self):
        self.sync_service = LGenieSyncService()

    def migrate_all_channels(self, batch_size: int = 100) -> Tuple[int, int]:
        """
        모든 채널을 LGenie DB로 마이그레이션

        Args:
            batch_size: 배치 처리 크기

        Returns:
            (성공한 채널 수, 전체 채널 수)
        """
        main_db = next(get_db())
        try:
            # 전체 채널 수 조회
            total_channels = main_db.query(ChatChannel).count()
            logger.info(f"마이그레이션 대상 채널 수: {total_channels}")

            success_count = 0
            offset = 0

            while offset < total_channels:
                # 배치 단위로 채널 조회
                channels = (
                    main_db.query(ChatChannel)
                    .order_by(desc(ChatChannel.id))
                    .offset(offset)
                    .limit(batch_size)
                    .all()
                )

                if not channels:
                    break

                # 각 채널 마이그레이션
                for channel in channels:
                    try:
                        if self.sync_service.sync_channel_with_messages(channel.id):
                            success_count += 1
                            logger.info(
                                f"채널 마이그레이션 성공: {channel.id} ({channel.session_id})"
                            )
                        else:
                            logger.error(
                                f"채널 마이그레이션 실패: {channel.id} ({channel.session_id})"
                            )
                    except Exception as e:
                        logger.error(f"채널 마이그레이션 중 오류: {channel.id} - {e}")

                offset += batch_size
                logger.info(f"진행상황: {offset}/{total_channels} 채널 처리 완료")

            logger.info(
                f"마이그레이션 완료: {success_count}/{total_channels} 채널 성공"
            )
            return success_count, total_channels

        except Exception as e:
            logger.error(f"마이그레이션 중 오류: {e}")
            return 0, 0
        finally:
            main_db.close()
            self.sync_service.close()

    def migrate_channels_by_date_range(
        self, start_date: str, end_date: str, batch_size: int = 100
    ) -> Tuple[int, int]:
        """
        특정 날짜 범위의 채널을 마이그레이션

        Args:
            start_date: 시작 날짜 (YYYY-MM-DD)
            end_date: 종료 날짜 (YYYY-MM-DD)
            batch_size: 배치 처리 크기

        Returns:
            (성공한 채널 수, 전체 채널 수)
        """
        main_db = next(get_db())
        try:
            from datetime import datetime
            from sqlalchemy import and_

            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")

            # 날짜 범위 내 채널 조회
            channels_query = main_db.query(ChatChannel).filter(
                and_(
                    ChatChannel.created_at >= start_datetime,
                    ChatChannel.created_at <= end_datetime,
                )
            )

            total_channels = channels_query.count()
            logger.info(
                f"날짜 범위 마이그레이션 대상 채널 수: {total_channels} ({start_date} ~ {end_date})"
            )

            success_count = 0
            offset = 0

            while offset < total_channels:
                # 배치 단위로 채널 조회
                channels = (
                    channels_query.order_by(desc(ChatChannel.id))
                    .offset(offset)
                    .limit(batch_size)
                    .all()
                )

                if not channels:
                    break

                # 각 채널 마이그레이션
                for channel in channels:
                    try:
                        if self.sync_service.sync_channel_with_messages(channel.id):
                            success_count += 1
                            logger.info(
                                f"채널 마이그레이션 성공: {channel.id} ({channel.session_id})"
                            )
                        else:
                            logger.error(
                                f"채널 마이그레이션 실패: {channel.id} ({channel.session_id})"
                            )
                    except Exception as e:
                        logger.error(f"채널 마이그레이션 중 오류: {channel.id} - {e}")

                offset += batch_size
                logger.info(f"진행상황: {offset}/{total_channels} 채널 처리 완료")

            logger.info(
                f"날짜 범위 마이그레이션 완료: {success_count}/{total_channels} 채널 성공"
            )
            return success_count, total_channels

        except Exception as e:
            logger.error(f"날짜 범위 마이그레이션 중 오류: {e}")
            return 0, 0
        finally:
            main_db.close()
            self.sync_service.close()

    def migrate_single_channel(self, channel_id: int) -> bool:
        """
        단일 채널 마이그레이션

        Args:
            channel_id: 마이그레이션할 채널 ID

        Returns:
            성공 여부
        """
        try:
            result = self.sync_service.sync_channel_with_messages(channel_id)
            if result:
                logger.info(f"단일 채널 마이그레이션 성공: {channel_id}")
            else:
                logger.error(f"단일 채널 마이그레이션 실패: {channel_id}")
            return result
        except Exception as e:
            logger.error(f"단일 채널 마이그레이션 중 오류: {channel_id} - {e}")
            return False
        finally:
            self.sync_service.close()

    def get_migration_stats(self) -> dict:
        """마이그레이션 통계 조회"""
        main_db = next(get_db())
        try:
            total_channels = main_db.query(ChatChannel).count()
            total_messages = main_db.query(ChatMessage).count()

            return {
                "total_channels": total_channels,
                "total_messages": total_messages,
            }
        except Exception as e:
            logger.error(f"통계 조회 중 오류: {e}")
            return {"total_channels": 0, "total_messages": 0}
        finally:
            main_db.close()


def main():
    """CLI 메인 함수"""
    parser = argparse.ArgumentParser(description="LGenie DB 마이그레이션 도구")
    parser.add_argument(
        "command",
        choices=["all", "date-range", "single", "stats"],
        help="실행할 명령어",
    )
    parser.add_argument(
        "--channel-id", type=int, help="단일 채널 마이그레이션 시 채널 ID"
    )
    parser.add_argument(
        "--start-date", help="날짜 범위 마이그레이션 시 시작 날짜 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end-date", help="날짜 범위 마이그레이션 시 종료 날짜 (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=100, help="배치 처리 크기 (기본값: 100)"
    )

    args = parser.parse_args()

    migration_service = LGenieMigrationService()

    if args.command == "all":
        logger.info("전체 채널 마이그레이션 시작")
        success_count, total_count = migration_service.migrate_all_channels(
            args.batch_size
        )
        logger.info(f"마이그레이션 완료: {success_count}/{total_count}")

    elif args.command == "date-range":
        if not args.start_date or not args.end_date:
            logger.error(
                "날짜 범위 마이그레이션에는 --start-date와 --end-date가 필요합니다"
            )
            return
        logger.info(f"날짜 범위 마이그레이션 시작: {args.start_date} ~ {args.end_date}")
        success_count, total_count = migration_service.migrate_channels_by_date_range(
            args.start_date, args.end_date, args.batch_size
        )
        logger.info(f"마이그레이션 완료: {success_count}/{total_count}")

    elif args.command == "single":
        if not args.channel_id:
            logger.error("단일 채널 마이그레이션에는 --channel-id가 필요합니다")
            return
        logger.info(f"단일 채널 마이그레이션 시작: {args.channel_id}")
        success = migration_service.migrate_single_channel(args.channel_id)
        logger.info(f"마이그레이션 결과: {'성공' if success else '실패'}")

    elif args.command == "stats":
        logger.info("마이그레이션 통계 조회")
        stats = migration_service.get_migration_stats()
        logger.info(f"통계: {stats}")


if __name__ == "__main__":
    main()
