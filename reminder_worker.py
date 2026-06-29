from __future__ import annotations

import sys
from database.db import SessionLocal, create_database
from services.telegram_service import (
    check_and_send_reminders,
    send_daily_digest,
    send_weekly_summary,
    send_afternoon_briefing,
    send_weekly_summary_for_week,
    send_monthly_report,
    send_pre_meeting_briefings,
)


def main() -> int:
    create_database()
    db = SessionLocal()
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "digest":
            ok = send_daily_digest(db)
            print(f"Daily digest sent: {ok}")
            return 1 if ok else 0

        if mode == "afternoon":
            ok = send_afternoon_briefing(db)
            print(f"Afternoon briefing sent: {ok}")
            return 1 if ok else 0

        if mode == "weekly":
            ok = send_weekly_summary_for_week(db, week_offset=0)
            print(f"Weekly summary sent: {ok}")
            return 1 if ok else 0

        if mode == "monthly":
            # sys.argv[2]로 year_month 지정 가능 (예: 2026-06), 없으면 전월 자동
            ym = sys.argv[2] if len(sys.argv) > 2 else None
            ok = send_monthly_report(db, ym)
            print(f"Monthly report sent: {ok}")
            return 1 if ok else 0

        # 기본 모드: 일정 알림 + 미팅 전 브리핑 동시 체크
        sent = check_and_send_reminders(db)
        briefings = send_pre_meeting_briefings(db)
        print(f"Telegram reminders sent: {sent}, briefings: {briefings}")
        return sent + briefings
    finally:
        db.close()


if __name__ == "__main__":
    main()
