from __future__ import annotations

import hashlib
import hmac
import os
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 server runtime
    import tomli as tomllib

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from database.db import SessionLocal, create_database
from database.models import Company, MeetingRecord, Schedule


APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "mobile_calendar"


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


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _auth_token() -> str:
    password_hash = _get_secret("APP_PASSWORD_HASH")
    username = _get_secret("APP_USERNAME", "admin")
    if not password_hash:
        return ""
    return hmac.new(password_hash.encode("utf-8"), username.encode("utf-8"), hashlib.sha256).hexdigest()


def _require_auth(authorization: str = Header(default="")) -> None:
    configured_token = _auth_token()
    if not configured_token:
        return
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, configured_token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class LoginPayload(BaseModel):
    username: str
    password: str


class SchedulePayload(BaseModel):
    title: str
    description: str | None = None
    start_date: date
    end_date: date
    start_time: str | None = None
    end_time: str | None = None
    all_day: bool = True
    color: str = "#2563EB"
    company_id: int | None = None
    remind_enabled: bool = True
    remind_minutes: int = 1440


app = FastAPI(title="Sales Intelligence Mobile Calendar")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def on_startup() -> None:
    create_database()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/login")
def login(payload: LoginPayload):
    expected_user = _get_secret("APP_USERNAME", "admin")
    password_hash = _get_secret("APP_PASSWORD_HASH")
    plain_password = _get_secret("APP_PASSWORD")
    if not password_hash and not plain_password:
        return {"token": "", "username": expected_user}
    user_ok = hmac.compare_digest(payload.username.strip(), expected_user)
    hash_ok = bool(password_hash) and hmac.compare_digest(_hash_password(payload.password), password_hash.strip().lower())
    plain_ok = bool(plain_password) and hmac.compare_digest(payload.password, plain_password)
    if not user_ok or not (hash_ok or plain_ok):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    return {"token": _auth_token(), "username": expected_user}


@app.get("/api/companies", dependencies=[Depends(_require_auth)])
def companies(db: Session = Depends(get_db)):
    rows = db.query(Company).order_by(Company.name).all()
    return [{"id": c.id, "name": c.name} for c in rows]


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    return (
        datetime(year, month, 1),
        datetime(year, month, monthrange(year, month)[1], 23, 59, 59),
    )


def _schedule_to_dict(s: Schedule):
    return {
        "id": s.id,
        "title": s.title,
        "description": s.description,
        "start_date": s.start_dt.date().isoformat(),
        "end_date": s.end_dt.date().isoformat(),
        "start_time": None if s.all_day else s.start_dt.strftime("%H:%M"),
        "end_time": None if s.all_day else s.end_dt.strftime("%H:%M"),
        "all_day": bool(s.all_day),
        "color": s.color or "#2563EB",
        "company_id": s.company_id,
        "company_name": s.company.name if s.company else "",
        "remind_enabled": bool(s.remind_enabled),
        "remind_minutes": s.remind_minutes or 1440,
        "remind_sent": bool(s.remind_sent),
    }


def _meeting_to_dict(m: MeetingRecord):
    return {
        "id": m.id,
        "meeting_date": m.meeting_date.isoformat() if m.meeting_date else None,
        "meeting_type": m.meeting_type,
        "attendees": m.attendees,
        "company_id": m.company_id,
        "company_name": m.company.name if m.company else "",
        "summary": m.analysis.one_line_summary if m.analysis else "",
    }


@app.get("/api/calendar/month", dependencies=[Depends(_require_auth)])
def calendar_month(year: int, month: int, company_id: int | None = None, db: Session = Depends(get_db)):
    start, end = _month_bounds(year, month)
    schedules_q = db.query(Schedule).options(joinedload(Schedule.company)).filter(
        Schedule.start_dt <= end,
        Schedule.end_dt >= start,
    )
    meetings_q = db.query(MeetingRecord).options(
        joinedload(MeetingRecord.company),
        joinedload(MeetingRecord.analysis),
    ).filter(
        MeetingRecord.meeting_date >= start.date(),
        MeetingRecord.meeting_date <= end.date(),
    )
    if company_id:
        schedules_q = schedules_q.filter(Schedule.company_id == company_id)
        meetings_q = meetings_q.filter(MeetingRecord.company_id == company_id)
    return {
        "schedules": [_schedule_to_dict(s) for s in schedules_q.order_by(Schedule.start_dt).all()],
        "meetings": [_meeting_to_dict(m) for m in meetings_q.order_by(MeetingRecord.meeting_date.desc()).all()],
    }


@app.get("/api/calendar/day", dependencies=[Depends(_require_auth)])
def calendar_day(day: date, company_id: int | None = None, db: Session = Depends(get_db)):
    day_start = datetime.combine(day, time.min)
    day_end = datetime.combine(day, time.max)
    schedules_q = db.query(Schedule).options(joinedload(Schedule.company)).filter(
        Schedule.start_dt <= day_end,
        Schedule.end_dt >= day_start,
    )
    meetings_q = db.query(MeetingRecord).options(
        joinedload(MeetingRecord.company),
        joinedload(MeetingRecord.analysis),
    ).filter(MeetingRecord.meeting_date == day)
    if company_id:
        schedules_q = schedules_q.filter(Schedule.company_id == company_id)
        meetings_q = meetings_q.filter(MeetingRecord.company_id == company_id)
    return {
        "schedules": [_schedule_to_dict(s) for s in schedules_q.order_by(Schedule.all_day.desc(), Schedule.start_dt).all()],
        "meetings": [_meeting_to_dict(m) for m in meetings_q.order_by(MeetingRecord.created_at.desc()).all()],
    }


def _payload_to_datetimes(payload: SchedulePayload) -> tuple[datetime, datetime]:
    if payload.all_day:
        return datetime.combine(payload.start_date, time.min), datetime.combine(payload.end_date, time.min)
    start_time = time.fromisoformat(payload.start_time or "09:00")
    end_time = time.fromisoformat(payload.end_time or "10:00")
    return datetime.combine(payload.start_date, start_time), datetime.combine(payload.end_date, end_time)


@app.post("/api/schedules", dependencies=[Depends(_require_auth)])
def create_schedule(payload: SchedulePayload, db: Session = Depends(get_db)):
    start_dt, end_dt = _payload_to_datetimes(payload)
    if end_dt < start_dt:
        raise HTTPException(status_code=400, detail="End datetime cannot be earlier than start datetime")
    row = Schedule(
        title=payload.title,
        description=payload.description,
        start_dt=start_dt,
        end_dt=end_dt,
        all_day=payload.all_day,
        color=payload.color,
        company_id=payload.company_id,
        remind_enabled=payload.remind_enabled,
        remind_minutes=payload.remind_minutes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _schedule_to_dict(row)


@app.put("/api/schedules/{schedule_id}", dependencies=[Depends(_require_auth)])
def update_schedule(schedule_id: int, payload: SchedulePayload, db: Session = Depends(get_db)):
    row = db.get(Schedule, schedule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    start_dt, end_dt = _payload_to_datetimes(payload)
    if end_dt < start_dt:
        raise HTTPException(status_code=400, detail="End datetime cannot be earlier than start datetime")
    row.title = payload.title
    row.description = payload.description
    row.start_dt = start_dt
    row.end_dt = end_dt
    row.all_day = payload.all_day
    row.color = payload.color
    row.company_id = payload.company_id
    row.remind_enabled = payload.remind_enabled
    row.remind_minutes = payload.remind_minutes
    row.remind_sent = False
    db.commit()
    db.refresh(row)
    return _schedule_to_dict(row)


@app.delete("/api/schedules/{schedule_id}", dependencies=[Depends(_require_auth)])
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    row = db.get(Schedule, schedule_id)
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(row)
    db.commit()
    return {"ok": True}
