from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests


def _get_token() -> str:
    return os.environ.get("TELEGRAM_BOT_TOKEN", "")


def _get_chat_id() -> str:
    return os.environ.get("TELEGRAM_CHAT_ID", "")


def send_message(text: str, chat_id: str | None = None) -> bool:
    token = _get_token()
    cid = chat_id or _get_chat_id()
    if not token or not cid:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": cid, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.ok
    except Exception:
        return False


def check_and_send_reminders(db) -> int:
    """미전송 알림 중 발송 시각이 된 것을 텔레그램으로 보내고 sent 처리. 전송 건수 반환."""
    from database.models import Schedule

    token = _get_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        return 0

    now = datetime.now()
    pending = (
        db.query(Schedule)
        .filter(
            Schedule.remind_enabled == True,
            Schedule.remind_sent == False,
        )
        .all()
    )

    sent = 0
    for s in pending:
        remind_at = s.start_dt - timedelta(minutes=s.remind_minutes)
        if now >= remind_at:
            company_str = f" [{s.company.name}]" if s.company else ""
            time_str = s.start_dt.strftime("%m/%d %H:%M") if not s.all_day else s.start_dt.strftime("%m/%d (종일)")
            text = (
                f"🔔 <b>일정 알림</b>{company_str}\n"
                f"📅 {time_str}\n"
                f"📌 {s.title}"
            )
            if s.description:
                text += f"\n📝 {s.description}"
            if send_message(text, chat_id):
                s.remind_sent = True
                sent += 1
    if sent:
        db.commit()
    return sent
