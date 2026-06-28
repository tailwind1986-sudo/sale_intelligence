from __future__ import annotations

import os
from datetime import datetime, timedelta
from html import escape
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
            timeout=30,
        )
        if not r.ok:
            print(f"Telegram send failed: HTTP {r.status_code} {r.text[:200]}")
        return r.ok
    except Exception as exc:
        print(f"Telegram send failed: {type(exc).__name__}")
        return False


def _schedule_time_text(schedule) -> str:
    if schedule.all_day:
        if schedule.start_dt.date() == schedule.end_dt.date():
            return schedule.start_dt.strftime("%Y-%m-%d 종일")
        return f"{schedule.start_dt.strftime('%Y-%m-%d')} ~ {schedule.end_dt.strftime('%Y-%m-%d')} 종일"
    if schedule.start_dt.date() == schedule.end_dt.date():
        return f"{schedule.start_dt.strftime('%Y-%m-%d %H:%M')} ~ {schedule.end_dt.strftime('%H:%M')}"
    return f"{schedule.start_dt.strftime('%Y-%m-%d %H:%M')} ~ {schedule.end_dt.strftime('%Y-%m-%d %H:%M')}"


def _reminder_label(minutes: int | None) -> str:
    labels = {
        0: "시작 시간",
        10: "10분 전",
        30: "30분 전",
        60: "1시간 전",
        180: "3시간 전",
        1440: "하루 전",
        10080: "일주일 전",
    }
    value = 0 if minutes is None else int(minutes)
    return labels.get(value, f"{value}분 전")


def send_schedule_created(schedule, chat_id: str | None = None) -> bool:
    """Notify Telegram when a new schedule is registered."""
    company_str = f" [{escape(schedule.company.name)}]" if getattr(schedule, "company", None) else ""
    lines = [
        f"<b>[신규일정등록]</b>{company_str}",
        f"시간: {escape(_schedule_time_text(schedule))}",
        f"제목: {escape(schedule.title or '-')}",
    ]
    if getattr(schedule, "remind_enabled", False):
        lines.append(f"사전 알림: {_reminder_label(schedule.remind_minutes)}")
    else:
        lines.append("사전 알림: 없음")
    if schedule.description:
        lines.append(f"메모: {escape(schedule.description)}")
    return send_message("\n".join(lines), chat_id)


def send_daily_digest(db) -> bool:
    """Send a morning briefing with today's schedule and near-term execution items."""
    from database.models import ActionItem, Promise, Schedule

    token = _get_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        return False

    now = _local_now_naive()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end   = now.replace(hour=23, minute=59, second=59, microsecond=0)
    deadline = now.date() + timedelta(days=7)

    schedules = (
        db.query(Schedule)
        .filter(Schedule.start_dt <= day_end, Schedule.end_dt >= day_start)
        .order_by(Schedule.all_day.desc(), Schedule.start_dt)
        .all()
    )

    actions = (
        db.query(ActionItem)
        .filter(
            ActionItem.status.in_(["예정", "진행중", "지연"]),
            ActionItem.due_date != None,
            ActionItem.due_date <= deadline,
        )
        .order_by(ActionItem.due_date)
        .limit(10)
        .all()
    )

    promises = (
        db.query(Promise)
        .filter(
            Promise.status.in_(["미확인", "진행중", "지연"]),
            Promise.due_date != None,
            Promise.due_date <= deadline,
        )
        .order_by(Promise.due_date)
        .limit(10)
        .all()
    )

    if not schedules and not actions and not promises:
        return False

    def _company_label(row) -> str:
        return f" [{escape(row.company.name)}]" if getattr(row, "company", None) else ""

    def _short(text: str | None, limit: int = 70) -> str:
        value = (text or "").strip()
        return escape(value[:limit] + ("…" if len(value) > limit else ""))

    lines = [f"☀️ <b>{now.month}월 {now.day}일 아침 브리핑</b>"]

    lines.append(f"\n<b>오늘 일정 ({len(schedules)}건)</b>")
    for s in schedules:
        if s.all_day:
            time_str = "종일"
        else:
            time_str = f"{s.start_dt.strftime('%H:%M')} ~ {s.end_dt.strftime('%H:%M')}"
        lines.append(f"• {time_str}{_company_label(s)} {_short(s.title)}")
    if not schedules:
        lines.append("• 오늘 등록된 일정 없음")

    lines.append(f"\n<b>7일 내 액션 ({len(actions)}건)</b>")
    for a in actions:
        due = a.due_date.strftime("%m/%d") if a.due_date else "기한미정"
        lines.append(f"• {due}{_company_label(a)} {_short(a.content)}")
    if not actions:
        lines.append("• 7일 내 마감 액션 없음")

    lines.append(f"\n<b>미확인 약속 ({len(promises)}건)</b>")
    for p in promises:
        due = p.due_date.strftime("%m/%d") if p.due_date else "기한미정"
        lines.append(f"• {due}{_company_label(p)} {_short(p.content)}")
    if not promises:
        lines.append("• 7일 내 확인할 약속 없음")

    return send_message("\n".join(lines), chat_id)


def send_weekly_summary(db) -> bool:
    """이번 주(월~금) 미팅 기록을 GPT-4o로 요약해 텔레그램 전송. 성공 시 True."""
    from database.models import MeetingRecord, MeetingAnalysis
    from sqlalchemy.orm import joinedload
    import json

    token = _get_token()
    chat_id = _get_chat_id()
    openai_key = _get_secret("OPENAI_API_KEY")
    if not token or not chat_id or not openai_key:
        print("Weekly summary skipped: missing token/chat_id/openai_key")
        return False

    now = _local_now_naive()
    # 이번 주 월요일 ~ 오늘(금요일)
    monday = now - timedelta(days=now.weekday())
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end   = now.replace(hour=23, minute=59, second=59, microsecond=0)

    from sqlalchemy import or_, cast, Date as SADate
    meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(
            or_(
                # meeting_date 컬럼이 있는 경우
                (MeetingRecord.meeting_date >= week_start.date()) &
                (MeetingRecord.meeting_date <= week_end.date()),
                # meeting_date 없으면 created_at 기준
                (MeetingRecord.meeting_date == None) &
                (MeetingRecord.created_at >= week_start) &
                (MeetingRecord.created_at <= week_end),
            )
        )
        .order_by(MeetingRecord.meeting_date, MeetingRecord.created_at)
        .all()
    )

    print(f"Weekly summary: found {len(meetings)} meetings ({week_start.date()} ~ {week_end.date()})")
    if not meetings:
        print("Weekly summary skipped: no meetings this week")
        return False

    # GPT에 넘길 미팅 내용 구성 (구조화 데이터 우선 활용)
    meeting_texts = []
    for m in meetings:
        date_str = m.meeting_date.strftime("%m/%d") if m.meeting_date else "날짜미상"
        company  = m.company.name if m.company else "미상"
        parts = [f"[{date_str}] {company}"]
        a = m.analysis
        if a:
            if a.one_line_summary:
                parts.append(f"요약: {a.one_line_summary}")
            if a.detailed_summary:
                parts.append(f"상세: {a.detailed_summary[:200]}")
            for label, field in [("핵심논의", a.key_discussions), ("결정사항", getattr(a, "decisions", None)),
                                  ("고객니즈", a.customer_needs), ("후속조치", a.follow_ups),
                                  ("리스크", a.risk_factors)]:
                if isinstance(field, list) and field:
                    parts.append(f"{label}: " + " / ".join(str(i) for i in field[:2]))
            if getattr(a, "action_items_structured", None):
                items = a.action_items_structured
                if isinstance(items, list):
                    action_strs = []
                    for item in items[:3]:
                        if isinstance(item, dict):
                            task = item.get("task", "")
                            due = item.get("due_date", "")
                            action_strs.append(f"{task}({due})" if due else task)
                    if action_strs:
                        parts.append("액션: " + " / ".join(action_strs))
        elif m.raw_text:
            parts.append(m.raw_text[:300])
        meeting_texts.append("\n".join(parts))

    week_label = f"{week_start.month}/{week_start.day}~{now.month}/{now.day}"
    prompt = f"""아래는 이번 주({week_label}) 영업 미팅 기록입니다.
주간 영업 보고서용으로 아래 형식에 맞게 작성해 주세요.

작성 규칙:
- 모든 항목은 명사형으로 끝맺음 (예: "~검토", "~확인 필요", "~예정")
- 소주제와 내용은 들여쓰기(공백 2칸) 적용
- 텔레그램 HTML 태그 사용: 주제는 <b>, 소주제는 <i>
- 불필요한 조사/접속사 제거, 핵심만 간결하게

출력 형식 (이 구조 그대로):
<b>📌 이번 주 핵심</b>
  • [핵심 내용 1줄]
  • [핵심 내용 1줄]

<b>🏢 고객사별 현황</b>
  <i>[고객사명]</i>
    - 주요논의: [내용]
    - 결정사항: [내용]
    - 후속조치: [내용]

<b>✅ 다음 주 액션</b>
  • [담당자/내용/기한]
  • [담당자/내용/기한]

미팅 기록:
{chr(10).join(meeting_texts)}"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        summary = resp.choices[0].message.content.strip()
    except Exception as exc:
        print(f"GPT weekly summary failed: {exc}")
        return False

    header = f"📊 <b>주간 영업 보고 ({week_label})</b>\n미팅 {len(meetings)}건\n\n"
    return send_message(header + summary, chat_id)


def send_weekly_summary_for_week(db, week_offset: int = 0) -> bool:
    """week_offset=0: 금주, -1: 지난주, -2: 2주전"""
    from database.models import MeetingRecord
    from sqlalchemy.orm import joinedload

    token = _get_token()
    chat_id = _get_chat_id()
    openai_key = _get_secret("OPENAI_API_KEY")
    if not token or not chat_id or not openai_key:
        return False

    now = _local_now_naive()
    monday = now - timedelta(days=now.weekday()) + timedelta(weeks=week_offset)
    week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = (monday + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=0)

    from sqlalchemy import or_
    meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(
            or_(
                (MeetingRecord.meeting_date >= week_start.date()) &
                (MeetingRecord.meeting_date <= week_end.date()),
                (MeetingRecord.meeting_date == None) &
                (MeetingRecord.created_at >= week_start) &
                (MeetingRecord.created_at <= week_end),
            )
        )
        .order_by(MeetingRecord.meeting_date, MeetingRecord.created_at)
        .all()
    )

    if not meetings:
        return False

    meeting_texts = []
    for m in meetings:
        date_str = m.meeting_date.strftime("%m/%d") if m.meeting_date else "날짜미상"
        company = m.company.name if m.company else "미상"
        parts = [f"[{date_str}] {company}"]
        a = m.analysis
        if a:
            if a.one_line_summary:
                parts.append(f"요약: {a.one_line_summary}")
            if a.detailed_summary:
                parts.append(f"상세: {a.detailed_summary[:200]}")
            for label, field in [("핵심논의", a.key_discussions), ("결정사항", getattr(a, "decisions", None)),
                                  ("후속조치", a.follow_ups), ("리스크", a.risk_factors)]:
                if isinstance(field, list) and field:
                    parts.append(f"{label}: " + " / ".join(str(i) for i in field[:2]))
        elif m.raw_text:
            parts.append(m.raw_text[:300])
        meeting_texts.append("\n".join(parts))

    week_label = f"{week_start.month}/{week_start.day}~{week_end.month}/{week_end.day}"
    prompt = f"""아래는 {week_label} 주간 영업 미팅 기록입니다.
주간 영업 보고서용으로 아래 형식에 맞게 작성해 주세요.

작성 규칙:
- 모든 항목은 명사형으로 끝맺음
- 텔레그램 HTML 태그 사용: 주제는 <b>, 소주제는 <i>
- 핵심만 간결하게

출력 형식:
<b>📌 이번 주 핵심</b>
  • [핵심 내용]

<b>🏢 고객사별 현황</b>
  <i>[고객사명]</i>
    - 주요논의: [내용]
    - 결정사항: [내용]
    - 후속조치: [내용]

<b>✅ 다음 주 액션</b>
  • [담당자/내용/기한]

미팅 기록:
{chr(10).join(meeting_texts)}"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        resp = client.chat.completions.create(
            model="gpt-4.1",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.3,
        )
        summary = resp.choices[0].message.content.strip()
    except Exception as exc:
        print(f"GPT weekly summary failed: {exc}")
        return False

    label_prefix = {0: "금주", -1: "지난주", -2: "2주전"}.get(week_offset, week_label)
    header = f"📊 <b>주간 영업 보고 [{label_prefix} {week_label}]</b>\n미팅 {len(meetings)}건\n\n"
    return send_message(header + summary, chat_id)


def send_afternoon_briefing(db) -> bool:
    """오후 브리핑: 오늘 입력된 회의록 정리 및 요약 전송"""
    from database.models import MeetingRecord
    from sqlalchemy.orm import joinedload

    token = _get_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        return False

    now = _local_now_naive()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = now.replace(hour=23, minute=59, second=59, microsecond=0)

    from sqlalchemy import or_
    meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(
            or_(
                (MeetingRecord.meeting_date == now.date()),
                (MeetingRecord.meeting_date == None) &
                (MeetingRecord.created_at >= day_start) &
                (MeetingRecord.created_at <= day_end),
            )
        )
        .order_by(MeetingRecord.created_at)
        .all()
    )

    lines = [f"🌆 <b>{now.month}월 {now.day}일 오후 브리핑</b>"]

    if not meetings:
        lines.append("\n오늘 입력된 회의록이 없습니다.")
        return send_message("\n".join(lines), chat_id)

    lines.append(f"\n<b>오늘 미팅 요약 ({len(meetings)}건)</b>")
    for m in meetings:
        company = escape(m.company.name if m.company else "미상")
        a = m.analysis
        lines.append(f"\n<i>🏢 {company}</i>")
        if a and a.one_line_summary:
            lines.append(f"• {escape(a.one_line_summary)}")
        if a and getattr(a, "decisions", None):
            decisions = a.decisions if isinstance(a.decisions, list) else []
            for d in decisions[:2]:
                lines.append(f"  ✅ {escape(str(d))}")
        if a and getattr(a, "action_items_structured", None):
            items = a.action_items_structured if isinstance(a.action_items_structured, list) else []
            for item in items[:3]:
                if isinstance(item, dict):
                    task = item.get("task", "")
                    assignee = item.get("assignee", "")
                    due = item.get("due_date", "")
                    lines.append(f"  → {escape(task)} / {escape(assignee)}" + (f" ({escape(due)})" if due else ""))
        if a and getattr(a, "risks_and_checks", None):
            risks = a.risks_and_checks if isinstance(a.risks_and_checks, list) else []
            for r in risks[:1]:
                lines.append(f"  ⚠️ {escape(str(r))}")

    return send_message("\n".join(lines), chat_id)


def send_daily_digest_for_date(db, target_date) -> bool:
    """특정 날짜의 회의록 정리 브리핑 전송 (오후 브리핑 스타일)"""
    from database.models import MeetingRecord
    from sqlalchemy.orm import joinedload

    token = _get_token()
    chat_id = _get_chat_id()
    if not token or not chat_id:
        return False

    from datetime import date as date_type
    if isinstance(target_date, str):
        target_date = date_type.fromisoformat(target_date)

    now = _local_now_naive()
    day_start = now.replace(year=target_date.year, month=target_date.month, day=target_date.day,
                            hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start.replace(hour=23, minute=59, second=59)

    from sqlalchemy import or_
    meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(
            or_(
                (MeetingRecord.meeting_date == target_date),
                (MeetingRecord.meeting_date == None) &
                (MeetingRecord.created_at >= day_start) &
                (MeetingRecord.created_at <= day_end),
            )
        )
        .order_by(MeetingRecord.created_at)
        .all()
    )

    date_str = target_date.strftime("%m월 %d일")
    lines = [f"📅 <b>{date_str} 회의록 정리</b>"]

    if not meetings:
        lines.append(f"\n해당 날짜에 입력된 회의록이 없습니다.")
        return send_message("\n".join(lines), chat_id)

    lines.append(f"\n<b>미팅 요약 ({len(meetings)}건)</b>")
    for m in meetings:
        company = escape(m.company.name if m.company else "미상")
        a = m.analysis
        lines.append(f"\n<i>🏢 {company}</i>")
        if a and a.one_line_summary:
            lines.append(f"• {escape(a.one_line_summary)}")
        if a and getattr(a, "decisions", None):
            for d in (a.decisions if isinstance(a.decisions, list) else [])[:2]:
                lines.append(f"  ✅ {escape(str(d))}")
        if a and getattr(a, "action_items_structured", None):
            for item in (a.action_items_structured if isinstance(a.action_items_structured, list) else [])[:3]:
                if isinstance(item, dict):
                    task = item.get("task", "")
                    assignee = item.get("assignee", "")
                    due = item.get("due_date", "")
                    lines.append(f"  → {escape(task)} / {escape(assignee)}" + (f" ({escape(due)})" if due else ""))
        if a and getattr(a, "risks_and_checks", None):
            for r in (a.risks_and_checks if isinstance(a.risks_and_checks, list) else [])[:1]:
                lines.append(f"  ⚠️ {escape(str(r))}")

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
            company_str = f" [{escape(s.company.name)}]" if s.company else ""
            text = (
                f"<b>[\uC77C\uC815\uC54C\uB9BC]</b>{company_str}\n"
                f"\uC2DC\uAC04: {escape(_schedule_time_text(s))}\n"
                f"\uC81C\uBAA9: {escape(s.title or '-')}\n"
                f"\uC54C\uB9BC \uC124\uC815: {_reminder_label(s.remind_minutes)}"
            )
            if s.description:
                text += f"\n\uBA54\uBAA8: {escape(s.description)}"
            if send_message(text, chat_id):
                s.remind_sent = True
                sent += 1
    if sent:
        db.commit()
    return sent
