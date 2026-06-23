from __future__ import annotations

from database.db import SessionLocal, create_database
from services.telegram_service import check_and_send_reminders


def main() -> int:
    create_database()
    db = SessionLocal()
    try:
        sent = check_and_send_reminders(db)
        print(f"Telegram reminders sent: {sent}")
        return sent
    finally:
        db.close()


if __name__ == "__main__":
    main()
