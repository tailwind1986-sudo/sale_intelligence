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

        sent = check_and_send_reminders(db)
        print(f"Telegram reminders sent: {sent}")
        return sent
    finally:
        db.close()


if __name__ == "__main__":
    main()
