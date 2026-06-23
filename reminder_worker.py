from __future__ import annotations

import sys
from database.db import SessionLocal, create_database
from services.telegram_service import check_and_send_reminders, send_daily_digest


def main() -> int:
    create_database()
    db = SessionLocal()
    try:
        # 아침 digest 모드: python reminder_worker.py digest
        if len(sys.argv) > 1 and sys.argv[1] == "digest":
            ok = send_daily_digest(db)
            print(f"Daily digest sent: {ok}")
            return 1 if ok else 0

        sent = check_and_send_reminders(db)
        print(f"Telegram reminders sent: {sent}")
        return sent
    finally:
        db.close()


if __name__ == "__main__":
    main()
