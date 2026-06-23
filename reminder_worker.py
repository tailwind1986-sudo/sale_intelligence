from __future__ import annotations

import sys
from database.db import SessionLocal, create_database
from services.telegram_service import check_and_send_reminders, send_daily_digest, send_weekly_summary


def main() -> int:
    create_database()
    db = SessionLocal()
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if mode == "digest":
            ok = send_daily_digest(db)
            print(f"Daily digest sent: {ok}")
            return 1 if ok else 0

        if mode == "weekly":
            ok = send_weekly_summary(db)
            print(f"Weekly summary sent: {ok}")
            return 1 if ok else 0

        sent = check_and_send_reminders(db)
        print(f"Telegram reminders sent: {sent}")
        return sent
    finally:
        db.close()


if __name__ == "__main__":
    main()
