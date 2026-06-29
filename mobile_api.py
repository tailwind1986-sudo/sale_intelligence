from __future__ import annotations

import hashlib
import hmac
import os
from calendar import monthrange
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

_KST = ZoneInfo("Asia/Seoul")

def _now_kst() -> datetime:
    return datetime.now(_KST).replace(tzinfo=None)

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 server runtime
    import tomli as tomllib

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified

load_dotenv()

from database.db import SessionLocal, create_database
from database.models import ActionItem, Company, CompanyHistory, Contact, CustomerInfo, IssueTag, MeetingAnalysis, MeetingRecord, MonthlyInsight, Promise, SalesSignal, Schedule
from services.ai_analyzer import analyze_meeting_transcript, generate_monthly_insight


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
    plain_password = _get_secret("APP_PASSWORD")
    username = _get_secret("APP_USERNAME", "admin")
    if not password_hash and plain_password:
        password_hash = _hash_password(plain_password)
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
app.mount("/mobile/static", StaticFiles(directory=STATIC_DIR), name="mobile_static")
app.mount("/mobile/workspace/static", StaticFiles(directory=WORKSPACE_DIR), name="mobile_workspace_static")


@app.middleware("http")
async def mobile_api_alias(request, call_next):
    if request.scope.get("path", "").startswith("/mobile/api/"):
        request.scope["path"] = request.scope["path"].replace("/mobile/api/", "/api/", 1)
    response = await call_next(request)
    path = request.scope.get("path", "")
    if path.startswith(("/mobile", "/static", "/workspace")) or path in {"/", "/sw.js"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.on_event("startup")
def on_startup() -> None:
    create_database()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/mobile/")
def mobile_index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/workspace")
def workspace_index():
    return FileResponse(WORKSPACE_DIR / "index.html")


@app.get("/mobile/workspace")
def mobile_workspace_index():
    return FileResponse(WORKSPACE_DIR / "index.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/mobile/"},
    )


@app.get("/mobile/sw.js")
def mobile_service_worker():
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
            joinedload(Company.issue_tags),
            joinedload(Company.history),
            joinedload(Company.sales_signals),
            joinedload(Company.monthly_insights),
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


@app.get("/api/workspace/hot-companies", dependencies=[Depends(_require_auth)])
def hot_companies(limit: int = 10, db: Session = Depends(get_db)):
    """최근 90일 영업 신호 기준 HOT 고객사 순위"""
    from datetime import date as _date
    today = _date.today()
    cutoff = today.replace(month=today.month - 3) if today.month > 3 \
        else today.replace(year=today.year - 1, month=today.month + 9)
    _w = {"HIGH": 3, "MED": 1, "LOW": 0}
    signals = (
        db.query(SalesSignal)
        .filter(SalesSignal.detected_at >= cutoff)
        .all()
    )
    from collections import defaultdict
    scores: dict[int, int] = defaultdict(int)
    sig_map: dict[int, list] = defaultdict(list)
    for s in signals:
        scores[s.company_id] += _w.get(s.strength, 0)
        sig_map[s.company_id].append(s.signal_type)
    if not scores:
        return []
    top_ids = sorted(scores, key=lambda cid: -scores[cid])[:limit]
    companies = db.query(Company).filter(Company.id.in_(top_ids)).all()
    company_map = {c.id: c for c in companies}
    result = []
    for cid in top_ids:
        c = company_map.get(cid)
        if not c:
            continue
        from collections import Counter
        top_signals = [st for st, _ in Counter(sig_map[cid]).most_common(3)]
        result.append({
            "id": cid,
            "name": c.name,
            "sales_stage": c.sales_stage or "",
            "hot_score": scores[cid],
            "top_signals": top_signals,
        })
    return result


@app.post("/api/workspace/monthly-insight/{company_id}", dependencies=[Depends(_require_auth)])
def generate_company_monthly_insight(company_id: int, db: Session = Depends(get_db), year_month: str | None = None):
    """특정 고객사의 월간 인사이트를 GPT로 생성/갱신."""
    import traceback
    try:
        return _do_generate_monthly_insight(company_id, db, year_month)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"[서버오류] {type(e).__name__}: {e}")


def _do_generate_monthly_insight(company_id: int, db, year_month):
    # monthly_insights 테이블이 없는 구버전 서버 DB 대비 — 필요 시 즉시 생성
    from database.db import create_database
    create_database()

    ym = year_month or _now_kst().strftime("%Y-%m")

    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 해당 월 미팅 요약 수집
    year, month = int(ym[:4]), int(ym[5:7])
    from sqlalchemy import extract
    month_meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.analysis))
        .filter(
            MeetingRecord.company_id == company_id,
            extract("year", MeetingRecord.meeting_date) == year,
            extract("month", MeetingRecord.meeting_date) == month,
        )
        .all()
    )
    meeting_summaries = [
        {
            "date": str(m.meeting_date) if m.meeting_date else "",
            "summary": (m.analysis.one_line_summary or "") if m.analysis else "",
        }
        for m in month_meetings
    ]

    if not meeting_summaries:
        raise HTTPException(
            status_code=400,
            detail=f"{ym} 에 분석된 미팅이 없어 인사이트를 생성할 수 없습니다."
        )

    # CompanyHistory 지표
    history_row = db.query(CompanyHistory).filter(
        CompanyHistory.company_id == company_id,
        CompanyHistory.year_month == ym,
    ).first()
    history_dict = None
    if history_row:
        history_dict = {
            "trust_score_avg": history_row.trust_score_avg,
            "risk_score_avg": history_row.risk_score_avg,
            "meeting_count": history_row.meeting_count,
            "sales_stage": history_row.sales_stage,
        }

    # 이전 인사이트 (최근 3개월)
    prev_insights_rows = (
        db.query(MonthlyInsight)
        .filter(
            MonthlyInsight.company_id == company_id,
            MonthlyInsight.year_month < ym,
        )
        .order_by(MonthlyInsight.year_month.desc())
        .limit(3)
        .all()
    )
    prev_insights = [
        {"year_month": p.year_month, "summary": p.summary or ""}
        for p in prev_insights_rows
    ]

    result = generate_monthly_insight(
        company_name=company.name,
        year_month=ym,
        meeting_summaries=meeting_summaries,
        company_history=history_dict,
        prev_insights=prev_insights,
    )

    # upsert
    existing = db.query(MonthlyInsight).filter(
        MonthlyInsight.company_id == company_id,
        MonthlyInsight.year_month == ym,
    ).first()
    if existing:
        existing.summary = result.get("summary")
        existing.key_trends = result.get("key_trends", [])
        existing.risks = result.get("risks", [])
        existing.opportunities = result.get("opportunities", [])
        existing.recommended_actions = result.get("recommended_actions", [])
        existing.relationship_score = result.get("relationship_score")
        existing.deal_probability = result.get("deal_probability")
        existing.updated_at = _now_kst()
    else:
        db.add(MonthlyInsight(
            company_id=company_id,
            year_month=ym,
            summary=result.get("summary"),
            key_trends=result.get("key_trends", []),
            risks=result.get("risks", []),
            opportunities=result.get("opportunities", []),
            recommended_actions=result.get("recommended_actions", []),
            relationship_score=result.get("relationship_score"),
            deal_probability=result.get("deal_probability"),
        ))
    db.commit()

    return {"ok": True, "year_month": ym, "result": result}


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
        "meeting_id": info.meeting_id,
        "detected_at": info.detected_at.isoformat() if info.detected_at else None,
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
        # 영업 기회 신호 (최근 90일, 최신순)
        from datetime import date as _date
        _cutoff = _date.today().replace(day=1)
        import calendar as _cal
        _cutoff = (_cutoff.replace(month=_cutoff.month - 3) if _cutoff.month > 3
                   else _cutoff.replace(year=_cutoff.year - 1, month=_cutoff.month + 9))
        _strength_order = {"HIGH": 0, "MED": 1, "LOW": 2}
        signals_raw = sorted(
            [s for s in (getattr(c, "sales_signals", []) or [])
             if s.detected_at and s.detected_at >= _cutoff],
            key=lambda s: (_strength_order.get(s.strength, 9), -(s.detected_at.toordinal() if s.detected_at else 0))
        )
        data["sales_signals"] = [
            {
                "signal_type": s.signal_type,
                "strength": s.strength,
                "content": s.content or "",
                "detected_at": s.detected_at.isoformat() if s.detected_at else "",
                "meeting_id": s.meeting_id,
            }
            for s in signals_raw[:20]
        ]
        # HOT 점수 (HIGH=3, MED=1, LOW=0)
        _w = {"HIGH": 3, "MED": 1, "LOW": 0}
        data["hot_score"] = sum(_w.get(s.strength, 0) for s in signals_raw)

        # 이슈 태그 집계
        from collections import Counter
        tags = getattr(c, "issue_tags", []) or []
        tag_counts = Counter(t.tag for t in tags if t.tag)
        data["issue_summary"] = [
            {"tag": tag, "count": cnt}
            for tag, cnt in sorted(tag_counts.items(), key=lambda x: -x[1])
        ]
        # 월별 히스토리
        history = sorted(getattr(c, "history", []) or [], key=lambda h: h.year_month)
        data["company_history"] = [
            {
                "year_month": h.year_month,
                "sales_stage": h.sales_stage or "",
                "trust_score_avg": h.trust_score_avg,
                "risk_score_avg": h.risk_score_avg,
                "mood_positive": h.mood_positive or 0,
                "mood_negative": h.mood_negative or 0,
                "meeting_count": h.meeting_count or 0,
            }
            for h in history[-12:]  # 최근 12개월
        ]
        # 월간 인사이트
        insights = sorted(getattr(c, "monthly_insights", []) or [], key=lambda x: x.year_month, reverse=True)
        data["monthly_insights"] = [
            {
                "id": ins.id,
                "year_month": ins.year_month,
                "summary": ins.summary or "",
                "key_trends": ins.key_trends or [],
                "risks": ins.risks or [],
                "opportunities": ins.opportunities or [],
                "recommended_actions": ins.recommended_actions or [],
                "relationship_score": ins.relationship_score,
                "deal_probability": ins.deal_probability,
                "updated_at": ins.updated_at.isoformat() if ins.updated_at else None,
            }
            for ins in insights[:6]  # 최근 6개월
        ]
    return data


def _brief_text(value: str | None, limit: int = 90) -> str:
    text = (value or "").strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _json_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return [value]


def _json_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _compact_meeting_report(meeting: MeetingRecord) -> str:
    analysis = meeting.analysis
    company = meeting.company.name if meeting.company else "-"
    meeting_date = meeting.meeting_date.isoformat() if meeting.meeting_date else "-"
    if not analysis:
        return f"[미팅보고] {company} / {meeting_date}\n\n주요논의\n- 분석 결과 대기"
    lines = [f"[미팅보고] {company} / {meeting_date}", "", "주요논의"]
    topics = _json_list(getattr(analysis, "topic_discussions", None))
    if topics:
        for item in topics[:5]:
            if isinstance(item, dict):
                topic = item.get("topic") or "주요 논의"
                desc = item.get("discussion") or item.get("current_status") or item.get("needs_review") or ""
                lines.append(f"- {topic}: {desc.strip()}")
            else:
                lines.append(f"- {str(item).strip()}")
    else:
        for item in _json_list(analysis.key_discussions)[:5]:
            lines.append(f"- {str(item).strip()}")
    checks = _json_list(getattr(analysis, "risks_and_checks", None)) or _json_list(analysis.pending_items)
    if checks:
        lines.extend(["", "확인필요"])
        lines.extend(f"- {str(item).strip()}" for item in checks[:3])
    return "\n".join(lines)


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


ANALYSIS_JSON_FIELDS = [
    "meeting_overview",
    "meeting_mood",
    "topic_discussions",
    "key_discussions",
    "decisions",
    "customer_needs",
    "complaints",
    "price_mentions",
    "competitor_mentions",
    "promises_raw",
    "follow_ups",
    "action_items_structured",
    "pending_items",
    "risk_factors",
    "risks_and_checks",
    "next_meeting_questions",
    "sales_opportunities",
    "relationship_notes",
    "schedule_candidates",
]


def _date_from_ai(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _add_generated_items(db: Session, record: MeetingRecord, result: dict) -> None:
    for p in result.get("promises", []) or []:
        if not isinstance(p, dict) or not p.get("content"):
            continue
        db.add(Promise(
            meeting_id=record.id,
            company_id=record.company_id,
            content=p.get("content", ""),
            promised_by=p.get("promised_by"),
            promised_date=record.meeting_date,
            due_date=_date_from_ai(p.get("due_date")),
            status="미확인",
        ))

    structured_actions = result.get("action_items_structured") or []
    if structured_actions:
        for item in structured_actions:
            if not isinstance(item, dict):
                continue
            content = item.get("task") or item.get("content") or ""
            if not content:
                continue
            assignee = item.get("assignee")
            db.add(ActionItem(
                meeting_id=record.id,
                company_id=record.company_id,
                content=content,
                assignee=assignee if assignee and assignee != "확인 필요" else None,
                due_date=_date_from_ai(item.get("due_date")),
                status="예정",
                notes=item.get("note"),
            ))
    else:
        for follow_up in result.get("follow_ups", []) or []:
            text = str(follow_up).strip()
            if not text:
                continue
            db.add(ActionItem(
                meeting_id=record.id,
                company_id=record.company_id,
                content=text,
                status="예정",
            ))


def _analysis_from_result(record: MeetingRecord, result: dict) -> MeetingAnalysis:
    return MeetingAnalysis(
        meeting_id=record.id,
        one_line_summary=result.get("one_line_summary"),
        detailed_summary=result.get("detailed_summary"),
        full_report=result.get("full_report"),
        analyzed_at=_now_kst(),
        meeting_overview=result.get("meeting_overview", {}),
        topic_discussions=result.get("topic_discussions", []),
        key_discussions=result.get("key_discussions", []),
        decisions=result.get("decisions", []),
        customer_needs=result.get("customer_needs", []),
        complaints=result.get("complaints", []),
        price_mentions=result.get("price_mentions", []),
        competitor_mentions=result.get("competitor_mentions", []),
        promises_raw=result.get("promises", []),
        follow_ups=result.get("follow_ups", []),
        action_items_structured=result.get("action_items_structured", []),
        pending_items=result.get("pending_items", []),
        risk_factors=result.get("risk_factors", []),
        risks_and_checks=result.get("risks_and_checks", []),
        next_meeting_questions=result.get("next_meeting_questions", []),
        sales_opportunities=result.get("sales_opportunities", []),
        relationship_notes=result.get("relationship_notes", []),
        schedule_candidates=result.get("schedule_candidates", []),
        meeting_mood=result.get("meeting_mood"),
        trust_score=result.get("trust_score", 50),
        risk_score=result.get("risk_score", 50),
    )


def _upsert_sales_signals(db: Session, record: MeetingRecord, result: dict) -> None:
    """회의록 분석 결과에서 SalesSignal 저장 (기존 것 삭제 후 재생성)."""
    db.query(SalesSignal).filter(SalesSignal.meeting_id == record.id).delete()
    signals = result.get("sales_signals") or []
    if not isinstance(signals, list):
        return
    detected_at = record.meeting_date or (record.created_at.date() if record.created_at else None)
    for item in signals:
        if not isinstance(item, dict):
            continue
        stype = (item.get("signal_type") or "").strip()
        if stype:
            db.add(SalesSignal(
                company_id=record.company_id,
                meeting_id=record.id,
                signal_type=stype,
                strength=item.get("strength") or "MED",
                content=item.get("content") or "",
                detected_at=detected_at,
            ))


def _upsert_issue_tags(db: Session, record: MeetingRecord, result: dict) -> None:
    """회의록 분석 결과에서 IssueTag 저장 (기존 것 삭제 후 재생성)."""
    db.query(IssueTag).filter(IssueTag.meeting_id == record.id).delete()
    tags = result.get("issue_tags") or []
    if isinstance(tags, list):
        for item in tags:
            if not isinstance(item, dict):
                continue
            tag = (item.get("tag") or "").strip()
            if tag:
                db.add(IssueTag(
                    company_id=record.company_id,
                    meeting_id=record.id,
                    tag=tag,
                    content=item.get("content") or "",
                ))


def _upsert_relationship_notes(db: Session, record: MeetingRecord, result: dict) -> None:
    """AI 분석 결과의 relationship_notes를 CustomerInfo에 자동 저장."""
    notes = result.get("relationship_notes") or []
    if not notes:
        return
    detected = record.meeting_date  # date 객체
    for item in notes:
        key = (item.get("key") or "").strip()
        value = (item.get("value") or "").strip()
        category = (item.get("category") or "기타").strip()
        if not key or not value:
            continue
        # 동일 company + key + value 가 이미 있으면 중복 저장 안 함
        # (같은 key라도 다른 value는 별도 항목으로 허용 — 예: "선호 음식: 삼겹살" vs "선호 음식: 초밥")
        duplicate = (
            db.query(CustomerInfo)
            .filter(
                CustomerInfo.company_id == record.company_id,
                CustomerInfo.key == key,
                CustomerInfo.value == value,
            )
            .first()
        )
        if duplicate:
            continue
        db.add(CustomerInfo(
            company_id=record.company_id,
            category=category,
            key=key,
            value=value,
            importance=item.get("importance", "보통"),
            notes=item.get("notes", ""),
            meeting_id=record.id,
            detected_at=detected,
        ))


def _upsert_company_history(db: Session, record: MeetingRecord, result: dict) -> None:
    """회의록 분석 결과로 해당 월 CompanyHistory 스냅샷 갱신."""
    if not record.company_id:
        return
    ref_date = record.meeting_date or (record.created_at.date() if record.created_at else None)
    if not ref_date:
        return
    ym = ref_date.strftime("%Y-%m")

    # 해당 월 전체 분석 완료 미팅 집계
    from sqlalchemy import extract
    month_analyses = (
        db.query(MeetingAnalysis)
        .join(MeetingRecord, MeetingAnalysis.meeting_id == MeetingRecord.id)
        .filter(
            MeetingRecord.company_id == record.company_id,
            extract("year", MeetingRecord.meeting_date) == ref_date.year,
            extract("month", MeetingRecord.meeting_date) == ref_date.month,
        )
        .all()
    )
    trust_scores = [a.trust_score for a in month_analyses if a.trust_score is not None]
    risk_scores  = [a.risk_score  for a in month_analyses if a.risk_score  is not None]
    moods = [
        (a.meeting_mood or {}).get("overall", "")
        for a in month_analyses
        if isinstance(a.meeting_mood, dict)
    ]
    mood_pos = sum(1 for m in moods if m == "긍정적")
    mood_neg = sum(1 for m in moods if m == "부정적")

    company = db.get(Company, record.company_id)
    history = db.query(CompanyHistory).filter(
        CompanyHistory.company_id == record.company_id,
        CompanyHistory.year_month == ym,
    ).first()
    if history:
        history.sales_stage     = company.sales_stage if company else history.sales_stage
        history.trust_score_avg = round(sum(trust_scores) / len(trust_scores), 1) if trust_scores else None
        history.risk_score_avg  = round(sum(risk_scores)  / len(risk_scores),  1) if risk_scores  else None
        history.mood_positive   = mood_pos
        history.mood_negative   = mood_neg
        history.meeting_count   = len(month_analyses)
        history.updated_at      = _now_kst()
    else:
        db.add(CompanyHistory(
            company_id      = record.company_id,
            year_month      = ym,
            sales_stage     = company.sales_stage if company else None,
            trust_score_avg = round(sum(trust_scores) / len(trust_scores), 1) if trust_scores else None,
            risk_score_avg  = round(sum(risk_scores)  / len(risk_scores),  1) if risk_scores  else None,
            mood_positive   = mood_pos,
            mood_negative   = mood_neg,
            meeting_count   = len(month_analyses),
        ))


def _save_meeting_analysis(db: Session, record: MeetingRecord, result: dict) -> None:
    db.add(_analysis_from_result(record, result))
    _add_generated_items(db, record, result)
    _upsert_sales_signals(db, record, result)
    _upsert_issue_tags(db, record, result)
    _upsert_company_history(db, record, result)
    _upsert_relationship_notes(db, record, result)
    db.commit()


def _update_meeting_analysis(analysis: MeetingAnalysis, result: dict, *, schedule_only: bool = False) -> None:
    if schedule_only:
        existing = _json_list(analysis.schedule_candidates)
        state_by_key = {
            (item.get("date"), item.get("title")): {
                key: item.get(key)
                for key in ("saved", "ignored")
                if item.get(key) is not None
            }
            for item in existing
            if isinstance(item, dict)
        }
        analysis.schedule_candidates = [
            {**item, **state_by_key.get((item.get("date"), item.get("title")), {})}
            for item in (result.get("schedule_candidates") or [])
            if isinstance(item, dict)
        ]
        flag_modified(analysis, "schedule_candidates")
        return

    analysis.one_line_summary = result.get("one_line_summary")
    analysis.detailed_summary = result.get("detailed_summary")
    analysis.full_report = result.get("full_report")
    analysis.analyzed_at = _now_kst()
    analysis.meeting_overview = result.get("meeting_overview", {})
    analysis.topic_discussions = result.get("topic_discussions", [])
    analysis.key_discussions = result.get("key_discussions", [])
    analysis.decisions = result.get("decisions", [])
    analysis.customer_needs = result.get("customer_needs", [])
    analysis.complaints = result.get("complaints", [])
    analysis.price_mentions = result.get("price_mentions", [])
    analysis.competitor_mentions = result.get("competitor_mentions", [])
    analysis.promises_raw = result.get("promises", [])
    analysis.follow_ups = result.get("follow_ups", [])
    analysis.action_items_structured = result.get("action_items_structured", [])
    analysis.pending_items = result.get("pending_items", [])
    analysis.risk_factors = result.get("risk_factors", [])
    analysis.risks_and_checks = result.get("risks_and_checks", [])
    analysis.next_meeting_questions = result.get("next_meeting_questions", [])
    analysis.sales_opportunities = result.get("sales_opportunities", [])
    analysis.relationship_notes = result.get("relationship_notes", [])
    analysis.schedule_candidates = result.get("schedule_candidates", [])
    analysis.meeting_mood = result.get("meeting_mood")
    analysis.trust_score = result.get("trust_score", 50)
    analysis.risk_score = result.get("risk_score", 50)
    for field in ANALYSIS_JSON_FIELDS:
        flag_modified(analysis, field)


def _analyze_record(db: Session, record: MeetingRecord, *, schedule_only: bool = False) -> None:
    if not record.raw_text or not record.raw_text.strip():
        raise HTTPException(status_code=400, detail="분석할 회의록 원문이 없습니다.")
    prev = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.analysis))
        .filter(MeetingRecord.company_id == record.company_id, MeetingRecord.id != record.id)
        .order_by(MeetingRecord.meeting_date.desc(), MeetingRecord.created_at.desc())
        .limit(3)
        .all()
    )
    result = analyze_meeting_transcript(record.raw_text, prev_meetings=prev)
    if record.analysis:
        _update_meeting_analysis(record.analysis, result, schedule_only=schedule_only)
        if not schedule_only:
            _upsert_sales_signals(db, record, result)
            _upsert_issue_tags(db, record, result)
            _upsert_company_history(db, record, result)
            _upsert_relationship_notes(db, record, result)
        db.commit()
    else:
        _save_meeting_analysis(db, record, result)


def _snippet(text: str | None, query: str, limit: int = 130) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    idx = value.lower().find(query.lower())
    if idx < 0:
        return _brief_text(value, limit)
    start = max(0, idx - 35)
    end = min(len(value), idx + limit)
    prefix = "..." if start else ""
    suffix = "..." if end < len(value) else ""
    return prefix + value[start:end] + suffix


@app.get("/api/search", dependencies=[Depends(_require_auth)])
def integrated_search(q: str, db: Session = Depends(get_db)):
    query = (q or "").strip()
    if len(query) < 2:
        return {"query": query, "total": 0, "groups": []}
    like = f"%{query}%"
    groups = []

    companies = (
        db.query(Company)
        .filter(or_(
            Company.name.ilike(like),
            Company.memo.ilike(like),
            Company.industry.ilike(like),
            Company.address.ilike(like),
            Company.website.ilike(like),
        ))
        .order_by(Company.name)
        .limit(20)
        .all()
    )
    groups.append({
        "type": "companies",
        "label": "고객사",
        "items": [
            {
                "id": row.id,
                "title": row.name,
                "meta": " · ".join(v for v in [row.business_type, row.sales_stage, row.industry] if v),
                "snippet": _snippet(row.memo or row.address or row.website, query),
            }
            for row in companies
        ],
    })

    contacts = (
        db.query(Contact)
        .options(joinedload(Contact.company))
        .filter(or_(
            Contact.name.ilike(like),
            Contact.position.ilike(like),
            Contact.phone.ilike(like),
            Contact.email.ilike(like),
            Contact.notes.ilike(like),
        ))
        .order_by(Contact.name)
        .limit(20)
        .all()
    )
    groups.append({
        "type": "contacts",
        "label": "담당자",
        "items": [
            {
                "id": row.id,
                "company_id": row.company_id,
                "title": row.name,
                "meta": " · ".join(v for v in [row.company.name if row.company else "", row.position, row.phone, row.email] if v),
                "snippet": _snippet(row.notes, query),
            }
            for row in contacts
        ],
    })

    meetings = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(or_(
            MeetingRecord.raw_text.ilike(like),
            MeetingRecord.attendees.ilike(like),
            MeetingRecord.memo.ilike(like),
            MeetingRecord.file_name.ilike(like),
            MeetingRecord.analysis.has(or_(
                MeetingAnalysis.one_line_summary.ilike(like),
                MeetingAnalysis.detailed_summary.ilike(like),
            )),
        ))
        .order_by(MeetingRecord.meeting_date.desc(), MeetingRecord.created_at.desc())
        .limit(30)
        .all()
    )
    groups.append({
        "type": "meetings",
        "label": "미팅/AI 요약",
        "items": [
            {
                "id": row.id,
                "company_id": row.company_id,
                "title": row.analysis.one_line_summary if row.analysis and row.analysis.one_line_summary else f"{row.company.name if row.company else '-'} 미팅",
                "meta": " · ".join(v for v in [
                    row.meeting_date.isoformat() if row.meeting_date else "",
                    row.company.name if row.company else "",
                    row.meeting_type or "",
                ] if v),
                "snippet": _snippet(
                    (row.analysis.detailed_summary if row.analysis else "") or row.raw_text or row.memo,
                    query,
                ),
            }
            for row in meetings
        ],
    })

    promises = (
        db.query(Promise)
        .options(joinedload(Promise.company))
        .filter(or_(
            Promise.content.ilike(like),
            Promise.promised_by.ilike(like),
            Promise.notes.ilike(like),
            Promise.status.ilike(like),
        ))
        .order_by(Promise.due_date)
        .limit(30)
        .all()
    )
    groups.append({
        "type": "promises",
        "label": "약속사항",
        "items": [
            {
                "id": row.id,
                "title": row.content,
                "meta": " · ".join(v for v in [row.company.name if row.company else "", row.status, row.due_date.isoformat() if row.due_date else ""] if v),
                "snippet": _snippet(row.notes, query),
            }
            for row in promises
        ],
    })

    actions = (
        db.query(ActionItem)
        .options(joinedload(ActionItem.company))
        .filter(or_(
            ActionItem.content.ilike(like),
            ActionItem.assignee.ilike(like),
            ActionItem.notes.ilike(like),
            ActionItem.status.ilike(like),
        ))
        .order_by(ActionItem.due_date)
        .limit(30)
        .all()
    )
    groups.append({
        "type": "actions",
        "label": "액션아이템",
        "items": [
            {
                "id": row.id,
                "title": row.content,
                "meta": " · ".join(v for v in [row.company.name if row.company else "", row.assignee, row.status, row.due_date.isoformat() if row.due_date else ""] if v),
                "snippet": _snippet(row.notes, query),
            }
            for row in actions
        ],
    })

    schedules = (
        db.query(Schedule)
        .options(joinedload(Schedule.company))
        .filter(or_(Schedule.title.ilike(like), Schedule.description.ilike(like)))
        .order_by(Schedule.start_dt.desc())
        .limit(30)
        .all()
    )
    groups.append({
        "type": "schedules",
        "label": "일정",
        "items": [
            {
                "id": row.id,
                "title": row.title,
                "meta": " · ".join(v for v in [
                    row.start_dt.strftime("%Y-%m-%d %H:%M") if row.start_dt else "",
                    row.company.name if row.company else "",
                    "종일" if row.all_day else "",
                ] if v),
                "snippet": _snippet(row.description, query),
            }
            for row in schedules
        ],
    })

    groups = [group for group in groups if group["items"]]
    return {"query": query, "total": sum(len(group["items"]) for group in groups), "groups": groups}


def _risk_row(company: Company) -> dict:
    breach = sum(1 for p in company.promises if p.status == "불이행")
    delayed_promises = sum(1 for p in company.promises if p.status == "지연")
    overdue_actions = sum(
        1 for item in company.action_items
        if item.due_date and item.due_date < date.today() and item.status != "완료"
    )
    risk_scores = [m.analysis.risk_score for m in company.meetings if m.analysis and m.analysis.risk_score is not None]
    trust_scores = [m.analysis.trust_score for m in company.meetings if m.analysis and m.analysis.trust_score is not None]
    avg_risk = round(sum(risk_scores) / len(risk_scores)) if risk_scores else 0
    avg_trust = round(sum(trust_scores) / len(trust_scores)) if trust_scores else 0
    composite = min(100, int(breach * 20 + delayed_promises * 10 + overdue_actions * 5 + avg_risk * 0.5))
    return {
        "id": company.id,
        "company": company.name,
        "business_type": company.business_type or "",
        "sales_stage": company.sales_stage or "",
        "risk_level": company.risk_level or "",
        "breach_promises": breach,
        "delayed_promises": delayed_promises,
        "overdue_actions": overdue_actions,
        "avg_risk": avg_risk,
        "avg_trust": avg_trust,
        "composite": composite,
    }


@app.get("/api/risk", dependencies=[Depends(_require_auth)])
def risk_dashboard(company_id: int | None = None, db: Session = Depends(get_db)):
    companies = (
        db.query(Company)
        .options(
            joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
            joinedload(Company.promises),
            joinedload(Company.action_items),
        )
        .order_by(Company.name)
        .all()
    )
    score_rows = sorted((_risk_row(row) for row in companies), key=lambda row: row["composite"], reverse=True)
    selected = None
    if companies:
        selected_company = next((row for row in companies if row.id == company_id), companies[0])
        risk_factors = []
        complaints = []
        competitors = []
        trend = []
        for meeting in sorted(selected_company.meetings, key=lambda row: row.meeting_date or date.min):
            analysis = meeting.analysis
            if not analysis:
                continue
            risk_factors.extend(str(item) for item in _json_list(analysis.risk_factors))
            complaints.extend(str(item) for item in _json_list(analysis.complaints))
            competitors.extend(str(item) for item in _json_list(analysis.competitor_mentions))
            trend.append({
                "date": meeting.meeting_date.isoformat() if meeting.meeting_date else "",
                "risk": analysis.risk_score or 0,
                "trust": analysis.trust_score or 0,
            })
        selected = {
            "id": selected_company.id,
            "company": selected_company.name,
            "risk_level": selected_company.risk_level or "",
            "risk_factors": risk_factors[-20:],
            "complaints": complaints[-20:],
            "competitors": competitors[-20:],
            "breaches": [
                {
                    "id": row.id,
                    "content": row.content,
                    "due_date": row.due_date.isoformat() if row.due_date else "",
                }
                for row in selected_company.promises
                if row.status == "불이행"
            ],
            "trend": trend[-12:],
        }
    return {"rows": score_rows, "selected": selected}


@app.post("/api/risk/{company_id}", dependencies=[Depends(_require_auth)])
def update_company_risk(company_id: int, payload: dict, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    risk_level = (payload.get("risk_level") or "").strip()
    if risk_level not in {"높음", "보통", "낮음"}:
        raise HTTPException(status_code=400, detail="Invalid risk level")
    company.risk_level = risk_level
    company.updated_at = datetime.now()
    db.commit()
    return {"ok": True}


@app.get("/api/telegram/status", dependencies=[Depends(_require_auth)])
def telegram_status():
    token = _get_secret("TELEGRAM_BOT_TOKEN")
    chat_id = _get_secret("TELEGRAM_CHAT_ID")
    return {
        "configured": bool(token and chat_id),
        "has_token": bool(token),
        "has_chat_id": bool(chat_id),
        "chat_id": chat_id if chat_id else "",
    }


@app.post("/api/telegram/test", dependencies=[Depends(_require_auth)])
def telegram_test():
    from services.telegram_service import send_message
    ok = send_message("Sales Intelligence 알림 테스트 메시지입니다.")
    return {"ok": bool(ok)}


@app.post("/api/telegram/check-reminders", dependencies=[Depends(_require_auth)])
def telegram_check_reminders(db: Session = Depends(get_db)):
    from services.telegram_service import check_and_send_reminders
    sent = check_and_send_reminders(db)
    return {"ok": True, "sent": sent}


@app.post("/api/telegram/daily-digest", dependencies=[Depends(_require_auth)])
def telegram_daily_digest(db: Session = Depends(get_db)):
    from services.telegram_service import send_daily_digest
    ok = send_daily_digest(db)
    return {"ok": bool(ok)}


@app.post("/api/telegram/weekly-summary", dependencies=[Depends(_require_auth)])
def telegram_weekly_summary(week_offset: int = 0, db: Session = Depends(get_db)):
    from services.telegram_service import send_weekly_summary_for_week
    ok = send_weekly_summary_for_week(db, week_offset=week_offset)
    return {"ok": bool(ok)}


@app.post("/api/telegram/afternoon-briefing", dependencies=[Depends(_require_auth)])
def telegram_afternoon_briefing(db: Session = Depends(get_db)):
    from services.telegram_service import send_afternoon_briefing
    ok = send_afternoon_briefing(db)
    return {"ok": bool(ok)}


@app.post("/api/telegram/date-briefing", dependencies=[Depends(_require_auth)])
def telegram_date_briefing(target_date: str, db: Session = Depends(get_db)):
    from services.telegram_service import send_daily_digest_for_date
    ok = send_daily_digest_for_date(db, target_date)
    return {"ok": bool(ok)}


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
    created = None
    if not _schedule_candidate_exists(db, meeting, candidate):
        created = _add_schedule_candidate(db, meeting, candidate)
    _update_schedule_candidate_state(meeting, index, **candidate, saved=True, ignored=False)
    db.commit()
    if created:
        db.refresh(created)
        try:
            from services.telegram_service import send_schedule_created
            send_schedule_created(created)
        except Exception as exc:
            print(f"Telegram schedule-created notification failed: {type(exc).__name__}")
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


@app.get("/api/meetings", dependencies=[Depends(_require_auth)])
def list_meeting_results(q: str = "", company_id: int | None = None, db: Session = Depends(get_db)):
    query = db.query(MeetingRecord).options(
        joinedload(MeetingRecord.company),
        joinedload(MeetingRecord.analysis),
        joinedload(MeetingRecord.action_items),
        joinedload(MeetingRecord.promises),
    )
    if company_id:
        query = query.filter(MeetingRecord.company_id == company_id)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (MeetingRecord.raw_text.ilike(like)) |
            (MeetingRecord.memo.ilike(like)) |
            (MeetingRecord.attendees.ilike(like)) |
            (MeetingRecord.analysis.has(MeetingAnalysis.one_line_summary.ilike(like)))
        )
    rows = query.order_by(MeetingRecord.meeting_date.desc(), MeetingRecord.created_at.desc()).limit(200).all()
    return [
        {
            "id": m.id,
            "company": m.company.name if m.company else "",
            "company_id": m.company_id,
            "meeting_date": m.meeting_date.isoformat() if m.meeting_date else "",
            "meeting_type": m.meeting_type or "",
            "attendees": m.attendees or "",
            "summary": _brief_text(m.analysis.one_line_summary if m.analysis else m.memo, 120),
            "has_analysis": bool(m.analysis),
            "mood_overall": (m.analysis.meeting_mood or {}).get("overall") if m.analysis and isinstance(m.analysis.meeting_mood, dict) else None,
            "actions": len(m.action_items),
            "promises": len(m.promises),
        }
        for m in rows
    ]


@app.post("/api/meetings/upload", dependencies=[Depends(_require_auth)])
async def upload_meeting_record(
    company_id: int = Form(...),
    meeting_date: date = Form(...),
    meeting_type: str = Form("방문"),
    attendees: str = Form(""),
    memo: str = Form(""),
    transcript: str = Form(""),
    run_ai: bool = Form(True),
    file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    raw_text = transcript.strip()
    file_name = ""
    if file and file.filename:
        body = await file.read()
        file_name = file.filename
        for encoding in ("utf-8-sig", "utf-8", "cp949"):
            try:
                raw_text = body.decode(encoding).strip()
                break
            except UnicodeDecodeError:
                continue
    if not raw_text:
        raise HTTPException(status_code=400, detail="전사 텍스트가 없습니다.")

    record = MeetingRecord(
        company_id=company_id,
        meeting_date=meeting_date,
        meeting_type=meeting_type or "방문",
        attendees=attendees.strip() or None,
        raw_text=raw_text,
        file_name=file_name or None,
        memo=memo.strip() or None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    ai_error = ""
    if run_ai:
        try:
            _analyze_record(db, record)
            db.refresh(record)
        except Exception as exc:
            ai_error = str(exc)
    return {
        "ok": True,
        "id": record.id,
        "has_analysis": bool(record.analysis),
        "ai_error": ai_error,
    }


@app.post("/api/meetings/{meeting_id}/analyze", dependencies=[Depends(_require_auth)])
def analyze_existing_meeting(meeting_id: int, schedule_only: bool = False, db: Session = Depends(get_db)):
    meeting = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.analysis))
        .filter(MeetingRecord.id == meeting_id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    _analyze_record(db, meeting, schedule_only=schedule_only)
    return {"ok": True}


@app.get("/api/meetings/{meeting_id}", dependencies=[Depends(_require_auth)])
def meeting_detail(meeting_id: int, db: Session = Depends(get_db)):
    meeting = (
        db.query(MeetingRecord)
        .options(
            joinedload(MeetingRecord.company),
            joinedload(MeetingRecord.analysis),
            joinedload(MeetingRecord.action_items),
            joinedload(MeetingRecord.promises),
        )
        .filter(MeetingRecord.id == meeting_id)
        .first()
    )
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    a = meeting.analysis
    return {
        "id": meeting.id,
        "company": meeting.company.name if meeting.company else "",
        "company_id": meeting.company_id,
        "meeting_date": meeting.meeting_date.isoformat() if meeting.meeting_date else "",
        "meeting_type": meeting.meeting_type or "",
        "attendees": meeting.attendees or "",
        "memo": meeting.memo or "",
        "raw_text": meeting.raw_text or "",
        "compact_report": _compact_meeting_report(meeting),
        "analysis": None if not a else {
            "one_line_summary": a.one_line_summary or "",
            "detailed_summary": a.detailed_summary or "",
            "full_report": a.full_report or "",
            "analyzed_at": a.analyzed_at.strftime("%Y-%m-%d %H:%M") if a.analyzed_at else (a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else ""),
            "meeting_overview": _json_dict(a.meeting_overview),
            "topic_discussions": _json_list(a.topic_discussions),
            "decisions": _json_list(a.decisions),
            "action_items_structured": _json_list(a.action_items_structured),
            "risks_and_checks": _json_list(a.risks_and_checks) or _json_list(a.risk_factors),
            "relationship_notes": _json_list(a.relationship_notes),
            "schedule_candidates": _json_list(a.schedule_candidates),
            "competitor_mentions": _json_list(a.competitor_mentions),
            "meeting_mood": _json_dict(a.meeting_mood) if isinstance(a.meeting_mood, dict) else {},
            "trust_score": a.trust_score or 0,
            "risk_score": a.risk_score or 0,
        },
        "actions": [_action_to_dict(row) for row in meeting.action_items],
        "promises": [_promise_to_dict(row) for row in meeting.promises],
    }


@app.post("/api/meetings/{meeting_id}/relationship-notes/{index}/save", dependencies=[Depends(_require_auth)])
def save_meeting_relationship_note(meeting_id: int, index: int, db: Session = Depends(get_db)):
    meeting = (
        db.query(MeetingRecord)
        .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
        .filter(MeetingRecord.id == meeting_id)
        .first()
    )
    if not meeting or not meeting.analysis:
        raise HTTPException(status_code=404, detail="Meeting not found")
    notes = _json_list(meeting.analysis.relationship_notes)
    if index < 0 or index >= len(notes) or not isinstance(notes[index], dict):
        raise HTTPException(status_code=404, detail="Relationship note not found")
    note = notes[index]
    sensitivity = note.get("sensitivity") or "낮음"
    db.add(CustomerInfo(
        company_id=meeting.company_id,
        category=note.get("category") or "고객 관계 정보",
        key=note.get("person_or_company") or meeting.company.name,
        value=note.get("content") or "",
        importance="높음" if sensitivity == "높음" else "보통",
        notes=f"활용 포인트: {note.get('use_point') or ''}\n민감도: {sensitivity}\n출처: {meeting.meeting_date.isoformat() if meeting.meeting_date else '-'} 회의록",
    ))
    db.commit()
    return {"ok": True}


@app.delete("/api/meetings/{meeting_id}", dependencies=[Depends(_require_auth)])
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.get(MeetingRecord, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    db.delete(meeting)
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
    try:
        from services.telegram_service import send_schedule_created
        send_schedule_created(row)
    except Exception as exc:
        print(f"Telegram schedule-created notification failed: {type(exc).__name__}")
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
