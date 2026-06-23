from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 server runtime
    import tomli as tomllib


APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TIMEZONE = "Asia/Seoul"

load_dotenv(APP_DIR / ".env")
load_dotenv()


def _read_secret_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_secret(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    for path in (
        APP_DIR / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ):
        data = _read_secret_file(path)
        if data.get(name):
            return str(data[name])
    return default


def _local_now_naive() -> datetime:
    timezone_name = _get_secret("APP_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        timezone = ZoneInfo(DEFAULT_TIMEZONE)
    return datetime.now(timezone).replace(tzinfo=None)


def _get_token() -> str:
    return _get_secret("TELEGRAM_BOT_TOKEN")


def _get_chat_id() -> str:
    return _get_secret("TELEGRAM_CHAT_ID")


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
        if not r.ok:
            print(f"Telegram send failed: HTTP {r.status_code} {r.text[:200]}")
        return r.ok
    except Exception as exc:
        print(f"Telegram send failed: {type(exc).__name__}")
        return False


def send_daily_digest(db) -> bool:
    """오늘 일정이 있을 때만 아침 요약 메시지 전송. 전송 성공 시 True."""
    from database.models import Schedule

    token = _get_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        return False

    now = _local_now_naive()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = now.replace(hour=23, minute=59, second=59, microsecond=0)

    schedules = (
        db.query(Schedule)
        .filter(Schedule.start_dt <= day_end, Schedule.end_dt >= day_start)
        .order_by(Schedule.all_day.desc(), Schedule.start_dt)
        .all()
    )

    if not schedules:
        return False

    lines = [f"☀️ <b>{now.month}월 {now.day}일 오늘의 일정 ({len(schedules)}건)</b>\n"]
    for s in schedules:
        if s.all_day:
            time_str = "종일"
        else:
            time_str = f"{s.start_dt.strftime('%H:%M')} ~ {s.end_dt.strftime('%H:%M')}"
        company_str = f" [{s.company.name}]" if s.company else ""
        lines.append(f"• {time_str}{company_str} {s.title}")

    return send_message("\n".join(lines), chat_id)


def check_and_send_reminders(db) -> int:
    """Send due Telegram reminders and mark them as sent."""
    from database.models import Schedule

    token = _get_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        print("Telegram reminder skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing")
        return 0

    now = _local_now_naive()
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
        remind_minutes = s.remind_minutes if s.remind_minutes is not None else 0
        remind_at = s.start_dt - timedelta(minutes=remind_minutes)
        if now >= remind_at:
            company_str = f" [{s.company.name}]" if s.company else ""
            time_str = s.start_dt.strftime("%m/%d 종일") if s.all_day else s.start_dt.strftime("%m/%d %H:%M")
            text = (
                f"<b>일정 알림</b>{company_str}\n"
                f"시간: {time_str}\n"
                f"제목: {s.title}"
            )
            if s.description:
                text += f"\n메모: {s.description}"
            if send_message(text, chat_id):
                s.remind_sent = True
                sent += 1
    if sent:
        db.commit()
    return sent
