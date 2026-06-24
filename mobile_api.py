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
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

load_dotenv()

from database.db import SessionLocal, create_database
from database.models import ActionItem, Company, Contact, CustomerInfo, MeetingAnalysis, MeetingRecord, Promise, Schedule


APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "mobile_calendar"
WORKSPACE_DIR = APP_DIR / "workspace_app"


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


class ActionPayload(BaseModel):
    company_id: int
    content: str
    assignee: str | None = None
    due_date: date | None = None
    status: str = "예정"
    notes: str | None = None


class PromisePayload(BaseModel):
    company_id: int
    content: str
    promised_by: str | None = None
    promised_date: date | None = None
    due_date: date | None = None
    status: str = "미확인"
    notes: str | None = None


class CompanyPayload(BaseModel):
    name: str
    business_type: str | None = None
    industry: str | None = None
    address: str | None = None
    website: str | None = None
    sales_stage: str | None = None
    expected_revenue: float | None = None
    importance: str | None = None
    risk_level: str | None = None
    memo: str | None = None


class ContactPayload(BaseModel):
    company_id: int
    name: str
    position: str | None = None
    phone: str | None = None
    email: str | None = None
    birthday: str | None = None
    is_primary: bool = False
    notes: str | None = None


class CustomerInfoPayload(BaseModel):
    company_id: int
    contact_id: int | None = None
    category: str | None = None
    key: str
    value: str
    importance: str = "보통"
    notes: str | None = None


app = FastAPI(title="Sales Intelligence Mobile Calendar")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/workspace/static", StaticFiles(directory=WORKSPACE_DIR), name="workspace_static")


@app.on_event("startup")
def on_startup() -> None:
    create_database()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workspace")
def workspace_index():
    return FileResponse(WORKSPACE_DIR / "index.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/mobile/"},
    )


@app.get("/static/")
def static_index_redirect():
    return Response(status_code=308, headers={"Location": "/"})


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


@app.get("/api/workspace/companies", dependencies=[Depends(_require_auth)])
def workspace_companies(
    q: str = "",
    business_type: str = "전체",
    sales_stage: str = "전체",
    risk_level: str = "전체",
    db: Session = Depends(get_db),
):
    query = db.query(Company).options(
        joinedload(Company.contacts),
        joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
        joinedload(Company.promises),
        joinedload(Company.action_items),
        joinedload(Company.customer_infos).joinedload(CustomerInfo.contact),
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Company.name.ilike(like)) |
            (Company.memo.ilike(like)) |
            (Company.industry.ilike(like)) |
            (Company.contacts.any(Contact.name.ilike(like)))
        )
    if business_type and business_type != "전체":
        query = query.filter(Company.business_type == business_type)
    if sales_stage and sales_stage != "전체":
        query = query.filter(Company.sales_stage == sales_stage)
    if risk_level and risk_level != "전체":
        query = query.filter(Company.risk_level == risk_level)
    rows = query.order_by(Company.name).limit(300).all()
    return [_company_to_dict(row) for row in rows]


@app.get("/api/workspace/companies/{company_id}", dependencies=[Depends(_require_auth)])
def workspace_company_detail(company_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(Company)
        .options(
            joinedload(Company.contacts),
            joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
            joinedload(Company.promises),
            joinedload(Company.action_items),
            joinedload(Company.customer_infos).joinedload(CustomerInfo.contact),
        )
        .filter(Company.id == company_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    return _company_to_dict(row, detail=True)


@app.post("/api/workspace/companies", dependencies=[Depends(_require_auth)])
def create_company(payload: CompanyPayload, db: Session = Depends(get_db)):
    row = Company(**payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _company_to_dict(row, detail=True)


@app.put("/api/workspace/companies/{company_id}", dependencies=[Depends(_require_auth)])
def update_company(company_id: int, payload: CompanyPayload, db: Session = Depends(get_db)):
    row = db.get(Company, company_id)
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    for key, value in payload.dict().items():
        setattr(row, key, value)
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _company_to_dict(row, detail=True)


@app.delete("/api/workspace/companies/{company_id}", dependencies=[Depends(_require_auth)])
def delete_company(company_id: int, db: Session = Depends(get_db)):
    row = db.get(Company, company_id)
    if not row:
        raise HTTPException(status_code=404, detail="Company not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/api/workspace/contacts", dependencies=[Depends(_require_auth)])
def create_contact(payload: ContactPayload, db: Session = Depends(get_db)):
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    row = Contact(**payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _contact_to_dict(row)


@app.put("/api/workspace/contacts/{contact_id}", dependencies=[Depends(_require_auth)])
def update_contact(contact_id: int, payload: ContactPayload, db: Session = Depends(get_db)):
    row = db.get(Contact, contact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    for key, value in payload.dict().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _contact_to_dict(row)


@app.delete("/api/workspace/contacts/{contact_id}", dependencies=[Depends(_require_auth)])
def delete_contact(contact_id: int, db: Session = Depends(get_db)):
    row = db.get(Contact, contact_id)
    if not row:
        raise HTTPException(status_code=404, detail="Contact not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/api/workspace/customer-infos", dependencies=[Depends(_require_auth)])
def create_customer_info(payload: CustomerInfoPayload, db: Session = Depends(get_db)):
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    row = CustomerInfo(**payload.dict())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _customer_info_to_dict(row)


@app.put("/api/workspace/customer-infos/{info_id}", dependencies=[Depends(_require_auth)])
def update_customer_info(info_id: int, payload: CustomerInfoPayload, db: Session = Depends(get_db)):
    row = db.get(CustomerInfo, info_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer info not found")
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    for key, value in payload.dict().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _customer_info_to_dict(row)


@app.delete("/api/workspace/customer-infos/{info_id}", dependencies=[Depends(_require_auth)])
def delete_customer_info(info_id: int, db: Session = Depends(get_db)):
    row = db.get(CustomerInfo, info_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer info not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


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


def _action_to_dict(a: ActionItem) -> dict:
    return {
        "id": a.id,
        "company_id": a.company_id,
        "company_name": a.company.name if a.company else "",
        "content": a.content,
        "assignee": a.assignee or "",
        "due_date": a.due_date.isoformat() if a.due_date else "",
        "status": a.status or "",
        "notes": a.notes or "",
        "is_overdue": bool(a.due_date and a.due_date < date.today() and a.status != "완료"),
    }


def _promise_to_dict(p: Promise) -> dict:
    return {
        "id": p.id,
        "company_id": p.company_id,
        "company_name": p.company.name if p.company else "",
        "content": p.content,
        "promised_by": p.promised_by or "",
        "promised_date": p.promised_date.isoformat() if p.promised_date else "",
        "due_date": p.due_date.isoformat() if p.due_date else "",
        "status": p.status or "",
        "notes": p.notes or "",
        "is_overdue": bool(p.due_date and p.due_date < date.today() and p.status != "완료"),
    }


def _contact_to_dict(c: Contact) -> dict:
    return {
        "id": c.id,
        "company_id": c.company_id,
        "name": c.name,
        "position": c.position or "",
        "phone": c.phone or "",
        "email": c.email or "",
        "birthday": c.birthday or "",
        "is_primary": bool(c.is_primary),
        "notes": c.notes or "",
    }


def _customer_info_to_dict(info: CustomerInfo) -> dict:
    return {
        "id": info.id,
        "company_id": info.company_id,
        "contact_id": info.contact_id,
        "contact_name": info.contact.name if info.contact else "",
        "category": info.category or "",
        "key": info.key,
        "value": info.value,
        "importance": info.importance or "",
        "notes": info.notes or "",
    }


def _company_to_dict(c: Company, detail: bool = False) -> dict:
    data = {
        "id": c.id,
        "name": c.name,
        "business_type": c.business_type or "",
        "industry": c.industry or "",
        "address": c.address or "",
        "website": c.website or "",
        "sales_stage": c.sales_stage or "",
        "expected_revenue": c.expected_revenue,
        "importance": c.importance or "",
        "risk_level": c.risk_level or "",
        "memo": c.memo or "",
        "meeting_count": len(c.meetings) if getattr(c, "meetings", None) is not None else 0,
        "action_count": len(c.action_items) if getattr(c, "action_items", None) is not None else 0,
        "promise_count": len(c.promises) if getattr(c, "promises", None) is not None else 0,
    }
    if detail:
        data["contacts"] = [_contact_to_dict(row) for row in c.contacts]
        data["customer_infos"] = [_customer_info_to_dict(row) for row in c.customer_infos]
        recent = sorted([m for m in c.meetings if m.meeting_date], key=lambda m: m.meeting_date, reverse=True)[:5]
        data["recent_meetings"] = [
            {
                "id": m.id,
                "date": m.meeting_date.isoformat() if m.meeting_date else "",
                "summary": _brief_text(m.analysis.one_line_summary if m.analysis else m.memo),
            }
            for m in recent
        ]
    return data


def _brief_text(value: str | None, limit: int = 90) -> str:
    text = (value or "").strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _parse_ai_date(value):
    if not value or str(value).strip() in {"확인 필요", "null", "None", "-"}:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _schedule_candidate_exists(db: Session, meeting: MeetingRecord, candidate: dict) -> bool:
    start_date = _parse_ai_date(candidate.get("date"))
    title = (candidate.get("title") or "").strip()
    if not start_date or not title:
        return False
    return db.query(Schedule).filter(
        Schedule.company_id == meeting.company_id,
        Schedule.title == title,
        Schedule.start_dt >= datetime.combine(start_date, time.min),
        Schedule.start_dt <= datetime.combine(start_date, time.max),
    ).first() is not None


def _add_schedule_candidate(db: Session, meeting: MeetingRecord, candidate: dict) -> Schedule:
    start_date = _parse_ai_date(candidate.get("date"))
    if not start_date:
        raise HTTPException(status_code=400, detail="Schedule candidate date is required")
    end_date = _parse_ai_date(candidate.get("end_date")) or start_date
    title = (candidate.get("title") or "회의록 추출 일정").strip()
    details = [
        f"프로젝트: {candidate.get('project') or '확인 필요'}",
        f"담당자: {candidate.get('assignee') or '확인 필요'}",
        f"장소: {candidate.get('location') or '확인 필요'}",
        f"비고: {candidate.get('note') or '-'}",
        f"출처: {meeting.meeting_date.isoformat() if meeting.meeting_date else '-'} {meeting.company.name if meeting.company else ''} 회의록",
    ]
    row = Schedule(
        title=title,
        description="\n".join(details),
        start_dt=datetime.combine(start_date, time(9, 0)),
        end_dt=datetime.combine(end_date, time(18, 0)),
        all_day=True,
        color="#0EA5E9",
        company_id=meeting.company_id,
        remind_enabled=True,
        remind_minutes=1440,
    )
    db.add(row)
    return row


def _update_schedule_candidate_state(meeting: MeetingRecord, index: int, **updates) -> None:
    analysis = meeting.analysis
    candidates = list(getattr(analysis, "schedule_candidates", None) or [])
    if index < 0 or index >= len(candidates) or not isinstance(candidates[index], dict):
        raise HTTPException(status_code=404, detail="Schedule candidate not found")
    candidates[index] = {**candidates[index], **updates}
    analysis.schedule_candidates = candidates
    flag_modified(analysis, "schedule_candidates")


@app.get("/api/dashboard", dependencies=[Depends(_require_auth)])
def dashboard(db: Session = Depends(get_db)):
    now = datetime.now()
    today = now.date()
    day_start = datetime.combine(today, time.min)
    day_end = datetime.combine(today, time.max)
    week_end = day_end + timedelta(days=7)

    today_schedules = (
        db.query(Schedule)
        .options(joinedload(Schedule.company))
        .filter(Schedule.start_dt <= day_end, Schedule.end_dt >= day_start)
        .order_by(Schedule.all_day.desc(), Schedule.start_dt)
        .limit(20)
        .all()
    )
    week_schedules = (
        db.query(Schedule)
        .options(joinedload(Schedule.company))
        .filter(Schedule.start_dt >= now, Schedule.start_dt <= week_end)
        .order_by(Schedule.start_dt)
        .limit(20)
        .all()
    )
    actions = (
        db.query(ActionItem)
        .options(joinedload(ActionItem.company))
        .filter(
            ActionItem.status.in_(["예정", "진행중", "지연"]),
            ActionItem.due_date != None,
            ActionItem.due_date <= week_end.date(),
        )
        .order_by(ActionItem.due_date)
        .limit(20)
        .all()
    )
    promises = (
        db.query(Promise)
        .options(joinedload(Promise.company))
        .filter(
            Promise.status.in_(["미확인", "진행중", "지연"]),
            Promise.due_date != None,
            Promise.due_date <= week_end.date(),
        )
        .order_by(Promise.due_date)
        .limit(20)
        .all()
    )
    recent_meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .order_by(MeetingRecord.meeting_date.desc(), MeetingRecord.created_at.desc())
        .limit(8)
        .all()
    )

    def schedule_item(s: Schedule) -> dict:
        return {
            "id": s.id,
            "title": s.title,
            "company": s.company.name if s.company else "",
            "date": s.start_dt.date().isoformat(),
            "time": "종일" if s.all_day else f"{s.start_dt.strftime('%H:%M')}~{s.end_dt.strftime('%H:%M')}",
            "color": s.color or "#2563EB",
        }

    return {
        "today": today.isoformat(),
        "metrics": {
            "today_schedules": len(today_schedules),
            "week_schedules": len(week_schedules),
            "due_actions": len(actions),
            "open_promises": len(promises),
        },
        "today_schedules": [schedule_item(s) for s in today_schedules],
        "week_schedules": [schedule_item(s) for s in week_schedules],
        "actions": [
            {
                "id": a.id,
                "company": a.company.name if a.company else "",
                "content": _brief_text(a.content),
                "assignee": a.assignee or "",
                "due_date": a.due_date.isoformat() if a.due_date else "",
                "status": a.status or "",
            }
            for a in actions
        ],
        "promises": [
            {
                "id": p.id,
                "company": p.company.name if p.company else "",
                "content": _brief_text(p.content),
                "promised_by": p.promised_by or "",
                "due_date": p.due_date.isoformat() if p.due_date else "",
                "status": p.status or "",
            }
            for p in promises
        ],
        "recent_meetings": [
            {
                "id": m.id,
                "company": m.company.name if m.company else "",
                "date": m.meeting_date.isoformat() if m.meeting_date else "",
                "summary": _brief_text(m.analysis.one_line_summary if m.analysis else m.memo),
            }
            for m in recent_meetings
        ],
    }


@app.get("/api/actions", dependencies=[Depends(_require_auth)])
def list_actions(
    status: str = "전체",
    company_id: int | None = None,
    assignee: str = "",
    db: Session = Depends(get_db),
):
    q = db.query(ActionItem).options(joinedload(ActionItem.company))
    if status and status != "전체":
        q = q.filter(ActionItem.status == status)
    if company_id:
        q = q.filter(ActionItem.company_id == company_id)
    if assignee:
        q = q.filter(ActionItem.assignee.ilike(f"%{assignee}%"))
    rows = q.order_by(ActionItem.due_date.is_(None), ActionItem.due_date).limit(300).all()
    return [_action_to_dict(row) for row in rows]


@app.post("/api/actions", dependencies=[Depends(_require_auth)])
def create_action(payload: ActionPayload, db: Session = Depends(get_db)):
    company = db.get(Company, payload.company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    row = ActionItem(
        company_id=payload.company_id,
        content=payload.content,
        assignee=payload.assignee,
        due_date=payload.due_date,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _action_to_dict(row)


@app.put("/api/actions/{action_id}", dependencies=[Depends(_require_auth)])
def update_action(action_id: int, payload: ActionPayload, db: Session = Depends(get_db)):
    row = db.get(ActionItem, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action item not found")
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    row.company_id = payload.company_id
    row.content = payload.content
    row.assignee = payload.assignee
    row.due_date = payload.due_date
    row.status = payload.status
    row.notes = payload.notes
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _action_to_dict(row)


@app.delete("/api/actions/{action_id}", dependencies=[Depends(_require_auth)])
def delete_action(action_id: int, db: Session = Depends(get_db)):
    row = db.get(ActionItem, action_id)
    if not row:
        raise HTTPException(status_code=404, detail="Action item not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.get("/api/promises", dependencies=[Depends(_require_auth)])
def list_promises(status: str = "전체", company_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Promise).options(joinedload(Promise.company))
    if status and status != "전체":
        q = q.filter(Promise.status == status)
    if company_id:
        q = q.filter(Promise.company_id == company_id)
    rows = q.order_by(Promise.due_date.is_(None), Promise.due_date).limit(300).all()
    return [_promise_to_dict(row) for row in rows]


@app.post("/api/promises", dependencies=[Depends(_require_auth)])
def create_promise(payload: PromisePayload, db: Session = Depends(get_db)):
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    row = Promise(
        company_id=payload.company_id,
        content=payload.content,
        promised_by=payload.promised_by,
        promised_date=payload.promised_date,
        due_date=payload.due_date,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _promise_to_dict(row)


@app.put("/api/promises/{promise_id}", dependencies=[Depends(_require_auth)])
def update_promise(promise_id: int, payload: PromisePayload, db: Session = Depends(get_db)):
    row = db.get(Promise, promise_id)
    if not row:
        raise HTTPException(status_code=404, detail="Promise not found")
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    row.company_id = payload.company_id
    row.content = payload.content
    row.promised_by = payload.promised_by
    row.promised_date = payload.promised_date
    row.due_date = payload.due_date
    row.status = payload.status
    row.notes = payload.notes
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _promise_to_dict(row)


@app.delete("/api/promises/{promise_id}", dependencies=[Depends(_require_auth)])
def delete_promise(promise_id: int, db: Session = Depends(get_db)):
    row = db.get(Promise, promise_id)
    if not row:
        raise HTTPException(status_code=404, detail="Promise not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.get("/api/schedule-candidates", dependencies=[Depends(_require_auth)])
def list_schedule_candidates(state: str = "pending", db: Session = Depends(get_db)):
    meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(MeetingRecord.analysis.has())
        .order_by(MeetingRecord.meeting_date.desc(), MeetingRecord.created_at.desc())
        .limit(250)
        .all()
    )
    rows = []
    for meeting in meetings:
        candidates = list(getattr(meeting.analysis, "schedule_candidates", None) or [])
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                continue
            saved = bool(candidate.get("saved") or _schedule_candidate_exists(db, meeting, candidate))
            ignored = bool(candidate.get("ignored"))
            row_state = "ignored" if ignored else ("saved" if saved else "pending")
            if state != "all" and row_state != state:
                continue
            rows.append({
                "meeting_id": meeting.id,
                "index": index,
                "state": row_state,
                "company": meeting.company.name if meeting.company else "",
                "meeting_date": meeting.meeting_date.isoformat() if meeting.meeting_date else "",
                "candidate": candidate,
            })
    return rows


@app.post("/api/schedule-candidates/{meeting_id}/{index}/save", dependencies=[Depends(_require_auth)])
def save_schedule_candidate(meeting_id: int, index: int, payload: dict, db: Session = Depends(get_db)):
    meeting = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(MeetingRecord.id == meeting_id)
        .first()
    )
    if not meeting or not meeting.analysis:
        raise HTTPException(status_code=404, detail="Meeting not found")
    candidates = list(meeting.analysis.schedule_candidates or [])
    if index < 0 or index >= len(candidates) or not isinstance(candidates[index], dict):
        raise HTTPException(status_code=404, detail="Schedule candidate not found")
    candidate = {**candidates[index], **payload}
    if not _schedule_candidate_exists(db, meeting, candidate):
        _add_schedule_candidate(db, meeting, candidate)
    _update_schedule_candidate_state(meeting, index, **candidate, saved=True, ignored=False)
    db.commit()
    return {"ok": True}


@app.post("/api/schedule-candidates/{meeting_id}/{index}/ignore", dependencies=[Depends(_require_auth)])
def ignore_schedule_candidate(meeting_id: int, index: int, db: Session = Depends(get_db)):
    meeting = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.analysis))
        .filter(MeetingRecord.id == meeting_id)
        .first()
    )
    if not meeting or not meeting.analysis:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _update_schedule_candidate_state(meeting, index, ignored=True)
    db.commit()
    return {"ok": True}


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
