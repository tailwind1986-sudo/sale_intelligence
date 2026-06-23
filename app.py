"""
Sales Intelligence System
영업 미팅 전사 분석 및 고객 관리 시스템
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import joinedload

load_dotenv()

from database.db import SessionLocal, create_database
from database.models import (
    ActionItem,
    Company,
    Contact,
    CustomerInfo,
    MeetingAnalysis,
    MeetingRecord,
    Promise,
    Schedule,
)
from services.ai_analyzer import analyze_meeting_transcript

# ─── 초기 설정 ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Sales Intelligence",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    create_database()
except Exception as _db_err:
    st.error(f"DB 연결 오류: {_db_err}")
    st.stop()


# ─── CSS ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* ══ 전체 레이아웃 ══ */
.main .block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1400px;
}

/* ══ 사이드바 ══ */
[data-testid="stSidebar"],
[data-testid="stSidebar"] > div:first-child,
[data-testid="stSidebar"] section {
    background-color: #0F172A !important;
}

/* 사이드바 버튼 기본 */
[data-testid="stSidebar"] button[kind="secondary"],
[data-testid="stSidebar"] .stButton > button {
    background-color: transparent !important;
    color: #94A3B8 !important;
    border: none !important;
    border-radius: 8px !important;
    text-align: left !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    padding: 0.55rem 1rem !important;
    margin: 1px 0 !important;
    transition: all 0.15s ease !important;
    box-shadow: none !important;
}

/* 사이드바 버튼 호버 */
[data-testid="stSidebar"] .stButton > button:hover {
    background-color: #1E293B !important;
    color: #E2E8F0 !important;
}

/* 사이드바 모든 텍스트 */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div {
    color: #94A3B8;
}

/* ══ 메트릭 카드 ══ */
.metric-card {
    background: #FFFFFF;
    border-radius: 12px;
    padding: 1.1rem 1.4rem;
    box-shadow: 0 1px 6px rgba(0,0,0,0.07);
    border-left: 4px solid #2563EB;
    margin-bottom: 0.5rem;
}
.metric-card h3 { margin: 0 0 4px; font-size: 1.9rem; font-weight: 700; }
.metric-card p  { margin: 0; color: #64748B; font-size: 0.82rem; font-weight: 500; }

/* ══ 섹션 타이틀 ══ */
.section-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1E293B;
    margin: 1.2rem 0 0.5rem;
    padding-bottom: 0.3rem;
    border-bottom: 2px solid #E2E8F0;
}

/* ══ 배지 ══ */
.badge-high   { display:inline-block; background:#FEE2E2; color:#B91C1C; padding:1px 9px; border-radius:99px; font-size:0.75rem; font-weight:700; }
.badge-medium { display:inline-block; background:#FEF9C3; color:#854D0E; padding:1px 9px; border-radius:99px; font-size:0.75rem; font-weight:700; }
.badge-low    { display:inline-block; background:#DCFCE7; color:#166534; padding:1px 9px; border-radius:99px; font-size:0.75rem; font-weight:700; }
.badge-info   { display:inline-block; background:#DBEAFE; color:#1D4ED8; padding:1px 9px; border-radius:99px; font-size:0.75rem; font-weight:700; }

/* ══ 타임라인 ══ */
.timeline-item {
    border-left: 3px solid #2563EB;
    padding-left: 1rem;
    margin-bottom: 1.4rem;
    position: relative;
}
.timeline-dot {
    width: 11px; height: 11px;
    background: #2563EB;
    border-radius: 50%;
    position: absolute;
    left: -7px; top: 5px;
}

/* ══ 점수 바 ══ */
.score-bar-wrap { background:#E2E8F0; border-radius:99px; height:7px; overflow:hidden; margin:4px 0 2px; }
.score-bar      { height:7px; border-radius:99px; }

/* ══ 행 구분선 ══ */
.row-divider { border-top: 1px solid #F1F5F9; margin: 6px 0; }
</style>
""", unsafe_allow_html=True)


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

@st.cache_resource
def _get_cached_session():
    """앱 전체에서 하나의 DB 세션을 재사용 (연결 오버헤드 제거)."""
    return SessionLocal()

def get_db():
    return _get_cached_session()


def risk_badge(level: str) -> str:
    m = {"높음": "badge-high", "보통": "badge-medium", "낮음": "badge-low"}
    return f'<span class="{m.get(level, "badge-info")}">{level}</span>'


def status_badge(status: str) -> str:
    m = {
        "완료": "badge-low", "진행중": "badge-info",
        "예정": "badge-medium", "지연": "badge-high",
        "불이행": "badge-high", "미확인": "badge-medium",
    }
    return f'<span class="{m.get(status, "badge-info")}">{status}</span>'


def score_bar(score: int, color: str = "#1E40AF") -> str:
    return f"""
<div class="score-bar-wrap">
  <div class="score-bar" style="width:{score}%;background:{color};"></div>
</div>
<small style="color:#64748B">{score}/100</small>"""


def fmt_date(d) -> str:
    if d is None:
        return "-"
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d")


SALES_STAGES = ["잠재", "접촉", "제안", "협상", "계약", "완료", "보류"]
BUSINESS_TYPES = ["CSO", "TLD", "기타"]
MEETING_TYPES = ["방문", "전화", "온라인", "기타"]
IMPORTANCE = ["높음", "보통", "낮음"]
PROMISE_STATUSES = ["미확인", "진행중", "완료", "지연", "불이행"]
ACTION_STATUSES = ["예정", "진행중", "완료", "지연"]
INFO_CATEGORIES = ["생일", "취향", "가족사항", "주요이슈", "알레르기/금기", "선물이력", "기타"]


# ─── 대시보드 ──────────────────────────────────────────────────────────────────

def page_dashboard():
    st.title("🏠 대시보드")

    db = get_db()
    try:
        total_companies = db.query(func.count(Company.id)).scalar() or 0
        total_meetings  = db.query(func.count(MeetingRecord.id)).scalar() or 0
        open_actions    = db.query(func.count(ActionItem.id)).filter(
            ActionItem.status.in_(["예정", "진행중"])
        ).scalar() or 0
        high_risk       = db.query(func.count(Company.id)).filter(
            Company.risk_level == "높음"
        ).scalar() or 0
        unfulfilled     = db.query(func.count(Promise.id)).filter(
            Promise.status == "불이행"
        ).scalar() or 0
        overdue_actions = db.query(func.count(ActionItem.id)).filter(
            ActionItem.status.in_(["예정", "진행중"]),
            ActionItem.due_date < date.today(),
        ).scalar() or 0

        # 지표 카드
        cols = st.columns(6)
        metrics = [
            ("고객사 수", total_companies, "#1E40AF"),
            ("총 미팅 수", total_meetings,  "#0F766E"),
            ("미완료 액션", open_actions,   "#7C3AED"),
            ("고위험 고객사", high_risk,    "#DC2626"),
            ("약속 불이행", unfulfilled,    "#EA580C"),
            ("기한 초과", overdue_actions,  "#B45309"),
        ]
        for col, (label, val, color) in zip(cols, metrics):
            with col:
                st.markdown(
                    f'<div class="metric-card" style="border-left-color:{color}">'
                    f'<h3 style="color:{color}">{val}</h3><p>{label}</p></div>',
                    unsafe_allow_html=True,
                )

        st.divider()
        col_l, col_r = st.columns(2)

        # 최근 미팅
        with col_l:
            st.markdown('<div class="section-title">📅 최근 미팅</div>', unsafe_allow_html=True)
            recent = (
                db.query(MeetingRecord)
                .options(joinedload(MeetingRecord.company), joinedload(MeetingRecord.analysis))
                .order_by(desc(MeetingRecord.meeting_date))
                .limit(7)
                .all()
            )
            if recent:
                rows = []
                for m in recent:
                    summary = m.analysis.one_line_summary if m.analysis else "분석 없음"
                    rows.append({
                        "날짜": fmt_date(m.meeting_date),
                        "고객사": m.company.name,
                        "유형": m.meeting_type or "-",
                        "요약": summary[:40] + "…" if summary and len(summary) > 40 else summary,
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            else:
                st.info("아직 미팅 기록이 없습니다.")

        # 기한 임박 액션아이템
        with col_r:
            st.markdown('<div class="section-title">⚡ 기한 임박 액션아이템 (7일 이내)</div>', unsafe_allow_html=True)
            deadline = date.today() + timedelta(days=7)
            urgent = (
                db.query(ActionItem)
                .filter(
                    ActionItem.status.in_(["예정", "진행중"]),
                    ActionItem.due_date <= deadline,
                )
                .order_by(ActionItem.due_date)
                .limit(8)
                .all()
            )
            if urgent:
                for a in urgent:
                    diff = (a.due_date - date.today()).days if a.due_date else 0
                    color = "#DC2626" if diff < 0 else ("#EA580C" if diff <= 2 else "#1E40AF")
                    st.markdown(
                        f'<div style="padding:6px 0;border-bottom:1px solid #EFF6FF">'
                        f'<b style="color:{color}">{fmt_date(a.due_date)}</b> '
                        f'<span style="color:#64748B">[{a.company.name}]</span> {a.content[:50]}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.success("7일 이내 마감 예정 액션아이템이 없습니다.")

        # 영업단계별 현황
        st.markdown('<div class="section-title">📊 영업단계별 고객사 현황</div>', unsafe_allow_html=True)
        stage_data = (
            db.query(Company.sales_stage, func.count(Company.id).label("count"))
            .group_by(Company.sales_stage)
            .all()
        )
        if stage_data:
            df_stage = pd.DataFrame(stage_data, columns=["단계", "수"])
            df_stage = df_stage[df_stage["단계"].notna()]
            # 단계 순서 정렬
            order = {s: i for i, s in enumerate(SALES_STAGES)}
            df_stage["_order"] = df_stage["단계"].map(lambda x: order.get(x, 99))
            df_stage = df_stage.sort_values("_order").drop(columns="_order")
            st.bar_chart(df_stage.set_index("단계"), use_container_width=True)
        else:
            st.info("고객사를 등록하면 현황이 표시됩니다.")

    finally:
        db.close()


# ─── 고객사 관리 ───────────────────────────────────────────────────────────────

def page_company_management():
    st.title("🏢 고객사 관리")

    db = get_db()
    try:
        # 수정 버튼 클릭 시 자동 섹션 전환을 위해 tabs 대신 radio 사용
        if "company_section" not in st.session_state:
            st.session_state["company_section"] = "고객사 목록"
        if st.session_state.get("edit_company_id") and st.session_state.get("_goto_edit"):
            st.session_state["company_section"] = "고객사 등록/수정"
            st.session_state.pop("_goto_edit", None)

        section = st.radio(
            "섹션",
            ["고객사 목록", "고객사 등록/수정", "담당자 관리", "고객 취향·중요정보"],
            horizontal=True,
            index=["고객사 목록", "고객사 등록/수정", "담당자 관리", "고객 취향·중요정보"].index(
                st.session_state["company_section"]
            ),
            key="company_section",
            label_visibility="collapsed",
        )
        st.divider()

        # ── 목록 ──
        if section == "고객사 목록":
            search = st.text_input("🔍 검색 (고객사명 / 담당자명)", key="company_search")
            filter_type  = st.selectbox("사업구분 필터", ["전체"] + BUSINESS_TYPES, key="f_type")
            filter_stage = st.selectbox("영업단계 필터", ["전체"] + SALES_STAGES, key="f_stage")
            filter_risk  = st.selectbox("리스크 필터", ["전체"] + IMPORTANCE, key="f_risk")

            q = db.query(Company).options(
                joinedload(Company.contacts),
                joinedload(Company.meetings),
                joinedload(Company.promises),
                joinedload(Company.action_items),
            )
            if search:
                q = q.filter(
                    or_(
                        Company.name.ilike(f"%{search}%"),
                        Company.contacts.any(Contact.name.ilike(f"%{search}%")),
                    )
                )
            if filter_type != "전체":
                q = q.filter(Company.business_type == filter_type)
            if filter_stage != "전체":
                q = q.filter(Company.sales_stage == filter_stage)
            if filter_risk != "전체":
                q = q.filter(Company.risk_level == filter_risk)

            companies = q.order_by(Company.name).all()
            st.caption(f"검색 결과: {len(companies)}개")

            for c in companies:
                primary = next((ct for ct in c.contacts if ct.is_primary), c.contacts[0] if c.contacts else None)
                meeting_count = len(c.meetings)
                with st.expander(f"**{c.name}** | {c.business_type or '-'} | {c.sales_stage or '-'} | 미팅 {meeting_count}회"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**담당자:** {primary.name if primary else '-'} ({primary.position if primary else ''})")
                        st.write(f"**연락처:** {primary.phone if primary else '-'}")
                    with col2:
                        st.write(f"**예상매출:** {f'{c.expected_revenue:,.0f}원' if c.expected_revenue else '-'}")
                        st.write(f"**중요도:** {c.importance or '-'}")
                    with col3:
                        st.markdown(f"**리스크:** {risk_badge(c.risk_level or '-')}", unsafe_allow_html=True)
                        st.write(f"**산업:** {c.industry or '-'}")
                    if c.memo:
                        st.write(f"**메모:** {c.memo}")

                    btn_col1, btn_col2 = st.columns(2)
                    if btn_col1.button("✏️ 수정", key=f"edit_{c.id}"):
                        st.session_state["edit_company_id"] = c.id
                        st.session_state["company_section"] = "고객사 등록/수정"
                        st.session_state["_goto_edit"] = True
                        st.rerun()
                    if btn_col2.button("🗑️ 삭제", key=f"del_{c.id}"):
                        st.session_state[f"confirm_del_{c.id}"] = True

                    if st.session_state.get(f"confirm_del_{c.id}"):
                        st.warning(f"'{c.name}'을(를) 정말 삭제하시겠습니까? 관련 미팅/약속/액션아이템이 모두 삭제됩니다.")
                        if st.button("확인 삭제", key=f"confirm2_{c.id}"):
                            db.delete(c)
                            db.commit()
                            st.toast("삭제되었습니다.", icon="🗑️")
                            st.rerun()

        # ── 등록/수정 ──
        if section == "고객사 등록/수정":
            edit_id = st.session_state.get("edit_company_id")
            editing = db.get(Company, edit_id) if edit_id else None

            st.subheader("고객사 수정" if editing else "신규 고객사 등록")

            with st.form("company_form", clear_on_submit=not editing):
                c1, c2 = st.columns(2)
                with c1:
                    name = st.text_input("고객사명 *", value=editing.name if editing else "")
                    business_type = st.selectbox("사업구분", BUSINESS_TYPES,
                        index=BUSINESS_TYPES.index(editing.business_type) if editing and editing.business_type in BUSINESS_TYPES else 0)
                    industry = st.text_input("산업/업종", value=editing.industry or "" if editing else "")
                    address = st.text_input("주소", value=editing.address or "" if editing else "")
                    website = st.text_input("웹사이트", value=editing.website or "" if editing else "")
                with c2:
                    sales_stage = st.selectbox("현재 영업단계", SALES_STAGES,
                        index=SALES_STAGES.index(editing.sales_stage) if editing and editing.sales_stage in SALES_STAGES else 0)
                    expected_revenue = st.number_input("예상매출 (원)", min_value=0,
                        value=int(editing.expected_revenue) if editing and editing.expected_revenue else 0, step=1000000)
                    importance = st.selectbox("중요도", IMPORTANCE,
                        index=IMPORTANCE.index(editing.importance) if editing and editing.importance in IMPORTANCE else 1)
                    risk_level = st.selectbox("리스크 등급", IMPORTANCE,
                        index=IMPORTANCE.index(editing.risk_level) if editing and editing.risk_level in IMPORTANCE else 1)
                memo = st.text_area("메모", value=editing.memo or "" if editing else "")

                submitted = st.form_submit_button("💾 저장")
                if submitted:
                    if not name:
                        st.error("고객사명은 필수입니다.")
                    else:
                        if editing:
                            editing.name = name
                            editing.business_type = business_type
                            editing.industry = industry or None
                            editing.address = address or None
                            editing.website = website or None
                            editing.sales_stage = sales_stage
                            editing.expected_revenue = expected_revenue or None
                            editing.importance = importance
                            editing.risk_level = risk_level
                            editing.memo = memo or None
                            editing.updated_at = datetime.now()
                        else:
                            c = Company(
                                name=name, business_type=business_type,
                                industry=industry or None, address=address or None,
                                website=website or None, sales_stage=sales_stage,
                                expected_revenue=expected_revenue or None,
                                importance=importance, risk_level=risk_level,
                                memo=memo or None,
                            )
                            db.add(c)
                        db.commit()
                        st.toast("저장되었습니다.", icon="✅")
                        st.session_state.pop("edit_company_id", None)
                        st.rerun()

            if editing and st.button("➕ 새 고객사 등록으로 전환"):
                st.session_state.pop("edit_company_id", None)
                st.rerun()

        # ── 담당자 관리 ──
        if section == "담당자 관리":
            companies_all = db.query(Company).options(
                joinedload(Company.contacts),
                joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
                joinedload(Company.promises),
                joinedload(Company.action_items),
                joinedload(Company.customer_infos),
            ).order_by(Company.name).all()
            if not companies_all:
                st.info("고객사를 먼저 등록해주세요.")
            else:
                sel_company = st.selectbox(
                    "고객사 선택", companies_all,
                    format_func=lambda x: x.name, key="contact_company"
                )

                st.subheader(f"담당자 목록 – {sel_company.name}")
                for ct in sel_company.contacts:
                    with st.expander(f"{'★ ' if ct.is_primary else ''}{ct.name} ({ct.position or '-'})"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"📞 {ct.phone or '-'}")
                            st.write(f"📧 {ct.email or '-'}")
                        with col2:
                            st.write(f"🎂 생일: {ct.birthday or '-'}")
                            st.write(f"📝 {ct.notes or '-'}")
                        if st.button("🗑️ 삭제", key=f"del_ct_{ct.id}"):
                            db.delete(ct)
                            db.commit()
                            st.rerun()

                st.divider()
                st.subheader("담당자 추가")
                with st.form("contact_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        ct_name     = st.text_input("이름 *")
                        ct_position = st.text_input("직책")
                        ct_phone    = st.text_input("연락처")
                    with c2:
                        ct_email    = st.text_input("이메일")
                        ct_birthday = st.text_input("생일 (예: 03-15 또는 1980-03-15)")
                        ct_primary  = st.checkbox("주담당자로 설정")
                    ct_notes = st.text_area("메모")

                    if st.form_submit_button("담당자 추가"):
                        if not ct_name:
                            st.error("이름은 필수입니다.")
                        else:
                            if ct_primary:
                                for existing in sel_company.contacts:
                                    existing.is_primary = False
                            db.add(Contact(
                                company_id=sel_company.id,
                                name=ct_name, position=ct_position or None,
                                phone=ct_phone or None, email=ct_email or None,
                                birthday=ct_birthday or None,
                                is_primary=ct_primary, notes=ct_notes or None,
                            ))
                            db.commit()
                            st.toast("담당자가 추가되었습니다.", icon="✅")
                            st.rerun()

        # ── 고객 취향·중요 정보 ──
        if section == "고객 취향·중요정보":
            companies_all2 = db.query(Company).options(
                joinedload(Company.contacts),
                joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
                joinedload(Company.promises),
                joinedload(Company.action_items),
                joinedload(Company.customer_infos),
            ).order_by(Company.name).all()
            if not companies_all2:
                st.info("고객사를 먼저 등록해주세요.")
            else:
                sel_company2 = st.selectbox(
                    "고객사 선택", companies_all2,
                    format_func=lambda x: x.name, key="info_company"
                )
                contacts_of = sel_company2.contacts

                st.subheader(f"고객 정보 – {sel_company2.name}")

                # 카테고리별 표시
                infos = db.query(CustomerInfo).filter(
                    CustomerInfo.company_id == sel_company2.id
                ).order_by(CustomerInfo.category, CustomerInfo.key).all()

                if infos:
                    df_info = pd.DataFrame([{
                        "카테고리": i.category or "-",
                        "항목": i.key,
                        "내용": i.value,
                        "중요도": i.importance,
                        "담당자": i.contact.name if i.contact else "고객사 전체",
                        "메모": i.notes or "",
                    } for i in infos])
                    st.dataframe(df_info, hide_index=True, use_container_width=True)

                    # 삭제
                    del_id = st.number_input("삭제할 항목 번호 (ID)", min_value=1, step=1, key="del_info_id", value=1)
                    if st.button("🗑️ 선택 항목 삭제"):
                        item = db.query(CustomerInfo).filter(
                            CustomerInfo.id == del_id,
                            CustomerInfo.company_id == sel_company2.id,
                        ).first()
                        if item:
                            db.delete(item)
                            db.commit()
                            st.toast("삭제되었습니다.", icon="🗑️")
                            st.rerun()
                        else:
                            st.error("해당 항목을 찾을 수 없습니다.")
                else:
                    st.info("등록된 정보가 없습니다.")

                st.divider()
                st.subheader("정보 추가")
                with st.form("info_form", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        info_cat = st.selectbox("카테고리", INFO_CATEGORIES)
                        info_key = st.text_input("항목명 (예: 좋아하는 음식, 골프 핸디캡)")
                        info_imp = st.selectbox("중요도", IMPORTANCE, index=1)
                    with c2:
                        ct_options = [None] + contacts_of
                        info_contact = st.selectbox(
                            "관련 담당자 (없으면 비워둠)",
                            ct_options,
                            format_func=lambda x: x.name if x else "고객사 전체",
                        )
                        info_value = st.text_area("내용")
                    info_notes = st.text_input("메모")

                    if st.form_submit_button("정보 추가"):
                        if not info_key or not info_value:
                            st.error("항목명과 내용은 필수입니다.")
                        else:
                            db.add(CustomerInfo(
                                company_id=sel_company2.id,
                                contact_id=info_contact.id if info_contact else None,
                                category=info_cat, key=info_key,
                                value=info_value, importance=info_imp,
                                notes=info_notes or None,
                            ))
                            db.commit()
                            st.toast("정보가 추가되었습니다.", icon="✅")
                            st.rerun()
    finally:
        db.close()


# ─── 미팅 기록 업로드 ──────────────────────────────────────────────────────────

def page_meeting_upload():
    st.title("📤 미팅 기록 업로드")

    db = get_db()
    try:
        companies_all = db.query(Company).options(
            joinedload(Company.contacts),
        ).order_by(Company.name).all()
        if not companies_all:
            st.warning("고객사를 먼저 등록해주세요.")
            return

        # ── STEP 1: 전사 텍스트 (form 밖 — file_uploader는 form 안에서 조건부 렌더링 시 submit 후 소실됨)
        st.markdown("### ① 전사 텍스트 입력")
        input_method = st.radio("입력 방식", ["TXT 파일 업로드", "직접 입력"], horizontal=True, key="up_method")

        if input_method == "TXT 파일 업로드":
            uploaded = st.file_uploader(
                "클로바노트 TXT 파일 (.txt)", type=["txt"], key="up_file",
                help="네이버 클로바노트에서 내보낸 .txt 파일을 업로드하세요"
            )
            if uploaded:
                raw_text = uploaded.read().decode("utf-8", errors="ignore")
                file_name = uploaded.name
                st.session_state["up_raw_text"] = raw_text
                st.session_state["up_file_name"] = file_name
                st.success(f"✅ 파일 로드 완료: **{file_name}** ({len(raw_text):,}자)")
                with st.expander("파일 내용 미리보기"):
                    st.text(raw_text[:800] + ("\n…(이하 생략)" if len(raw_text) > 800 else ""))
            elif "up_raw_text" not in st.session_state:
                st.info("TXT 파일을 선택하면 내용이 자동으로 로드됩니다.")
        else:
            direct = st.text_area(
                "미팅 내용 직접 입력", height=250, key="up_direct",
                placeholder="미팅에서 나눈 대화 내용을 자유롭게 입력하세요…"
            )
            st.session_state["up_raw_text"] = direct
            st.session_state["up_file_name"] = ""

        # 현재 로드된 텍스트 확인
        current_text = st.session_state.get("up_raw_text", "")
        if current_text:
            st.caption(f"📝 현재 로드된 텍스트: {len(current_text):,}자")

        st.divider()

        # ── STEP 2: 미팅 기본 정보 (form)
        st.markdown("### ② 미팅 기본 정보")
        with st.form("upload_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                sel_company = st.selectbox("고객사 *", companies_all, format_func=lambda x: x.name)
                meeting_date = st.date_input("미팅 일자 *", value=date.today())
                meeting_type = st.selectbox("미팅 유형", MEETING_TYPES)
            with c2:
                attendees = st.text_input("참석자 (쉼표 구분)", placeholder="홍길동, 이순신")
                memo = st.text_area("메모 / 특이사항", height=100)
                run_ai = st.checkbox("저장 후 AI 분석 자동 실행", value=True)

            submitted = st.form_submit_button("💾 저장", use_container_width=True, type="primary")

        # ── STEP 3: 저장 처리
        if submitted:
            raw_text = st.session_state.get("up_raw_text", "")
            file_name = st.session_state.get("up_file_name", "")

            if not raw_text.strip():
                st.error("전사 텍스트가 없습니다. 먼저 파일을 업로드하거나 직접 입력해주세요.")
            else:
                record = MeetingRecord(
                    company_id=sel_company.id,
                    meeting_date=meeting_date,
                    meeting_type=meeting_type,
                    attendees=attendees or None,
                    raw_text=raw_text,
                    file_name=file_name or None,
                    memo=memo or None,
                )
                db.add(record)
                db.commit()
                db.refresh(record)

                # 저장 후 텍스트 초기화
                st.session_state.pop("up_raw_text", None)
                st.session_state.pop("up_file_name", None)

                st.toast(f"미팅 기록 저장 완료! (ID: {record.id})", icon="✅")

                if run_ai:
                    with st.spinner("🤖 AI 분석 중… (30초~1분 소요)"):
                        try:
                            result = analyze_meeting_transcript(raw_text)
                            _save_analysis(db, record, result)
                            st.toast("AI 분석 완료! '미팅 요약 결과' 메뉴에서 확인하세요.", icon="🎉")
                            st.session_state["last_meeting_id"] = record.id
                        except Exception as e:
                            st.toast(f"AI 분석 오류: {e}", icon="❌")
                            st.info("'미팅 요약 결과' 메뉴에서 수동으로 분석을 실행할 수 있습니다.")
                            st.session_state["last_meeting_id"] = record.id
                else:
                    st.info("'미팅 요약 결과' 메뉴에서 수동으로 분석을 실행하세요.")
                    st.session_state["last_meeting_id"] = record.id
    finally:
        db.close()


def _save_analysis(db, record: MeetingRecord, result: dict) -> None:
    """AI 분석 결과를 DB에 저장하고 약속/액션아이템을 추출한다."""
    analysis = MeetingAnalysis(
        meeting_id=record.id,
        one_line_summary=result.get("one_line_summary"),
        detailed_summary=result.get("detailed_summary"),
        key_discussions=result.get("key_discussions", []),
        customer_needs=result.get("customer_needs", []),
        complaints=result.get("complaints", []),
        price_mentions=result.get("price_mentions", []),
        competitor_mentions=result.get("competitor_mentions", []),
        promises_raw=result.get("promises", []),
        follow_ups=result.get("follow_ups", []),
        pending_items=result.get("pending_items", []),
        risk_factors=result.get("risk_factors", []),
        next_meeting_questions=result.get("next_meeting_questions", []),
        sales_opportunities=result.get("sales_opportunities", []),
        trust_score=result.get("trust_score", 50),
        risk_score=result.get("risk_score", 50),
    )
    db.add(analysis)

    # 약속사항 자동 생성
    for p in result.get("promises", []):
        due = None
        raw_due = p.get("due_date")
        if raw_due:
            try:
                due = datetime.strptime(raw_due, "%Y-%m-%d").date()
            except Exception:
                pass
        db.add(Promise(
            meeting_id=record.id,
            company_id=record.company_id,
            content=p.get("content", ""),
            promised_by=p.get("promised_by"),
            promised_date=record.meeting_date,
            due_date=due,
            status="미확인",
        ))

    # 후속조치 → 액션아이템 자동 생성
    for fu in result.get("follow_ups", []):
        db.add(ActionItem(
            meeting_id=record.id,
            company_id=record.company_id,
            content=fu,
            status="예정",
        ))

    db.commit()


# ─── 미팅 요약 결과 ────────────────────────────────────────────────────────────

def page_meeting_results():
    st.title("📋 미팅 요약 결과")

    db = get_db()
    try:
        meetings = (
            db.query(MeetingRecord)
            .options(
                joinedload(MeetingRecord.company),
                joinedload(MeetingRecord.analysis),
                joinedload(MeetingRecord.promises),
                joinedload(MeetingRecord.action_items),
            )
            .order_by(desc(MeetingRecord.meeting_date))
            .all()
        )
        if not meetings:
            st.info("미팅 기록이 없습니다.")
            return

        # 선택
        default_id = st.session_state.get("last_meeting_id")
        default_idx = 0
        if default_id:
            ids = [m.id for m in meetings]
            if default_id in ids:
                default_idx = ids.index(default_id)

        sel_meeting = st.selectbox(
            "미팅 선택",
            meetings,
            index=default_idx,
            format_func=lambda m: f"{fmt_date(m.meeting_date)} | {m.company.name} | {m.meeting_type or '-'}",
        )

        # 미팅 삭제
        with st.expander("⚠️ 이 미팅 삭제"):
            st.warning(f"**{fmt_date(sel_meeting.meeting_date)} | {sel_meeting.company.name}** 미팅을 삭제하면 분석결과·약속·액션아이템이 모두 삭제됩니다.")
            if st.button("🗑️ 미팅 삭제 확인", type="primary"):
                meeting_to_del = db.get(MeetingRecord, sel_meeting.id)
                if meeting_to_del:
                    db.delete(meeting_to_del)
                    db.commit()
                st.session_state.pop("last_meeting_id", None)
                st.toast("삭제되었습니다.", icon="🗑️")
                st.rerun()

        # 수동 분석 트리거
        if not sel_meeting.analysis:
            st.warning("이 미팅은 아직 AI 분석이 실행되지 않았습니다.")
            if st.button("🤖 AI 분석 실행"):
                with st.spinner("분석 중…"):
                    try:
                        result = analyze_meeting_transcript(sel_meeting.raw_text)
                        _save_analysis(db, sel_meeting, result)
                        st.toast("분석 완료!", icon="🎉")
                        st.rerun()
                    except Exception as e:
                        st.toast(f"오류: {e}", icon="❌")
            return

        a = sel_meeting.analysis
        company = sel_meeting.company

        # 헤더
        hcol1, hcol2, hcol3, hcol4 = st.columns(4)
        hcol1.metric("신뢰도", f"{a.trust_score}/100")
        hcol2.metric("위험도", f"{a.risk_score}/100")
        hcol3.metric("약속", f"{len(sel_meeting.promises)}건")
        hcol4.metric("액션", f"{len(sel_meeting.action_items)}건")

        # 점수 바
        col_t, col_r = st.columns(2)
        with col_t:
            trust_color = "#10B981" if a.trust_score >= 70 else ("#F59E0B" if a.trust_score >= 40 else "#EF4444")
            st.markdown(f"**신뢰도 점수**{score_bar(a.trust_score, trust_color)}", unsafe_allow_html=True)
        with col_r:
            risk_color = "#EF4444" if a.risk_score >= 70 else ("#F59E0B" if a.risk_score >= 40 else "#10B981")
            st.markdown(f"**위험도 점수**{score_bar(a.risk_score, risk_color)}", unsafe_allow_html=True)

        st.divider()

        # 요약
        st.subheader("📝 요약")
        st.info(f"**한 줄 요약:** {a.one_line_summary or '-'}")
        if a.detailed_summary:
            st.write(a.detailed_summary)

        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📌 핵심내용", "🤝 약속·액션", "⚠️ 리스크·불만", "💡 기회·질문", "📄 원문"])

        with tab1:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**주요 논의사항**")
                for item in (a.key_discussions or []):
                    st.write(f"• {item}")
                st.markdown("**고객 니즈**")
                for item in (a.customer_needs or []):
                    st.write(f"• {item}")
            with c2:
                st.markdown("**가격 언급**")
                for item in (a.price_mentions or []):
                    st.write(f"• {item}")
                st.markdown("**경쟁사 언급**")
                for item in (a.competitor_mentions or []):
                    st.write(f"• {item}")
                st.markdown("**미결 사항**")
                for item in (a.pending_items or []):
                    st.write(f"• {item}")

        with tab2:
            st.markdown("**약속사항**")
            for p in sel_meeting.promises:
                st.markdown(
                    f"- {status_badge(p.status)} **{p.content}** "
                    f"(약속자: {p.promised_by or '-'}, 기한: {fmt_date(p.due_date)})",
                    unsafe_allow_html=True,
                )
                p_cols = st.columns([3, 1])
                new_status = p_cols[1].selectbox(
                    "상태 변경", PROMISE_STATUSES, index=PROMISE_STATUSES.index(p.status),
                    key=f"ps_{p.id}", label_visibility="collapsed"
                )
                if new_status != p.status:
                    p.status = new_status
                    db.commit()
                    st.rerun()

            st.divider()
            st.markdown("**액션아이템**")
            for ai in sel_meeting.action_items:
                st.markdown(
                    f"- {status_badge(ai.status)} {ai.content} "
                    f"(담당: {ai.assignee or '-'}, 기한: {fmt_date(ai.due_date)})",
                    unsafe_allow_html=True,
                )
                a_cols = st.columns([3, 1])
                new_as = a_cols[1].selectbox(
                    "상태", ACTION_STATUSES, index=ACTION_STATUSES.index(ai.status),
                    key=f"as_{ai.id}", label_visibility="collapsed"
                )
                if new_as != ai.status:
                    ai.status = new_as
                    db.commit()
                    st.rerun()

            # 수동 액션아이템 추가
            with st.expander("➕ 액션아이템 수동 추가"):
                with st.form("add_action_meeting", clear_on_submit=True):
                    ai_content  = st.text_input("내용")
                    ai_assignee = st.text_input("담당자")
                    ai_due      = st.date_input("기한")
                    if st.form_submit_button("추가"):
                        db.add(ActionItem(
                            meeting_id=sel_meeting.id, company_id=sel_meeting.company_id,
                            content=ai_content, assignee=ai_assignee or None, due_date=ai_due,
                        ))
                        db.commit()
                        st.toast("추가되었습니다.", icon="✅")
                        st.rerun()

        with tab3:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**불만·우려사항**")
                for item in (a.complaints or []):
                    st.write(f"⚠️ {item}")
            with c2:
                st.markdown("**리스크 요인**")
                for item in (a.risk_factors or []):
                    st.write(f"🔴 {item}")

        with tab4:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**영업 기회**")
                for item in (a.sales_opportunities or []):
                    st.write(f"💚 {item}")
            with c2:
                st.markdown("**다음 미팅 질문**")
                for item in (a.next_meeting_questions or []):
                    st.write(f"❓ {item}")

        with tab5:
            st.text_area("원문 전사 텍스트", sel_meeting.raw_text or "", height=400, disabled=True)

    finally:
        db.close()


# ─── 고객사별 타임라인 ────────────────────────────────────────────────────────

def page_timeline():
    st.title("📅 고객사별 타임라인")

    db = get_db()
    try:
        companies_all = db.query(Company).options(
                joinedload(Company.contacts),
                joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
                joinedload(Company.promises),
                joinedload(Company.action_items),
                joinedload(Company.customer_infos),
            ).order_by(Company.name).all()
        if not companies_all:
            st.info("고객사를 먼저 등록해주세요.")
            return

        sel_company = st.selectbox("고객사 선택", companies_all, format_func=lambda x: x.name)

        # 고객사 요약 정보
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("영업단계", sel_company.sales_stage or "-")
        col2.metric("사업구분", sel_company.business_type or "-")
        col3.metric("중요도", sel_company.importance or "-")
        col4.metric("총 미팅", len(sel_company.meetings))

        # 고객 취향 정보 요약
        infos = db.query(CustomerInfo).filter(CustomerInfo.company_id == sel_company.id).all()
        if infos:
            with st.expander(f"⭐ 고객 정보 ({len(infos)}건)"):
                for info in infos:
                    ct_name = info.contact.name if info.contact else "고객사 전체"
                    st.markdown(
                        f"**[{info.category}] {info.key}**: {info.value} "
                        f"<span style='color:#64748B;font-size:0.85rem'>({ct_name})</span>",
                        unsafe_allow_html=True,
                    )

        st.divider()

        # 타임라인
        meetings = (
            db.query(MeetingRecord)
            .options(
                joinedload(MeetingRecord.analysis),
                joinedload(MeetingRecord.promises),
            )
            .filter(MeetingRecord.company_id == sel_company.id)
            .order_by(desc(MeetingRecord.meeting_date))
            .all()
        )

        if not meetings:
            st.info("이 고객사의 미팅 기록이 없습니다.")
            return

        for m in meetings:
            a = m.analysis
            trust_str = f"신뢰 {a.trust_score}/100" if a else "미분석"
            risk_str  = f"위험 {a.risk_score}/100"  if a else ""

            st.markdown(
                f'<div class="timeline-item">'
                f'<div class="timeline-dot"></div>'
                f'<b>{fmt_date(m.meeting_date)}</b> '
                f'<span class="badge-info">{m.meeting_type or "기타"}</span> '
                f'<span style="color:#64748B;font-size:0.85rem">{trust_str} | {risk_str}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            with st.expander(f"{'📋 ' + a.one_line_summary if a and a.one_line_summary else '상세 보기'}", expanded=False):
                if a:
                    if a.detailed_summary:
                        st.write(a.detailed_summary)
                    c1, c2 = st.columns(2)
                    with c1:
                        if a.customer_needs:
                            st.markdown("**고객 니즈**")
                            for n in a.customer_needs:
                                st.write(f"• {n}")
                        if a.competitor_mentions:
                            st.markdown("**경쟁사 언급**")
                            for n in a.competitor_mentions:
                                st.write(f"• {n}")
                    with c2:
                        if a.risk_factors:
                            st.markdown("**리스크 요인**")
                            for n in a.risk_factors:
                                st.write(f"• {n}")
                        if a.follow_ups:
                            st.markdown("**후속조치**")
                            for n in a.follow_ups:
                                st.write(f"• {n}")

                # 약속사항 표시
                if m.promises:
                    st.markdown("**약속사항**")
                    for p in m.promises:
                        icon = {"완료": "✅", "불이행": "❌", "지연": "⏰", "진행중": "🔄"}.get(p.status, "📋")
                        st.markdown(
                            f"{icon} {status_badge(p.status)} {p.content} "
                            f"<span style='color:#64748B'>(기한: {fmt_date(p.due_date)})</span>",
                            unsafe_allow_html=True,
                        )

        # 약속 불이행 추적
        st.divider()
        st.subheader("📊 약속 이행 현황")
        all_promises = db.query(Promise).filter(Promise.company_id == sel_company.id).all()
        if all_promises:
            status_counts = {}
            for p in all_promises:
                status_counts[p.status] = status_counts.get(p.status, 0) + 1
            df_p = pd.DataFrame(list(status_counts.items()), columns=["상태", "건수"])
            st.bar_chart(df_p.set_index("상태"), use_container_width=True)
        else:
            st.info("약속사항이 없습니다.")

    finally:
        db.close()


# ─── 액션아이템 관리 ───────────────────────────────────────────────────────────

def page_action_items():
    st.title("✅ 액션아이템 관리")

    db = get_db()
    try:
        tab_action, tab_promise = st.tabs(["액션아이템", "약속사항"])

        # ── 액션아이템 ──
        with tab_action:
            c1, c2, c3 = st.columns(3)
            with c1:
                filter_status = st.selectbox("상태 필터", ["전체"] + ACTION_STATUSES)
            with c2:
                companies_all = db.query(Company).options(
                joinedload(Company.contacts),
                joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
                joinedload(Company.promises),
                joinedload(Company.action_items),
                joinedload(Company.customer_infos),
            ).order_by(Company.name).all()
                filter_company_a = st.selectbox(
                    "고객사 필터", [None] + companies_all,
                    format_func=lambda x: x.name if x else "전체", key="fa_company"
                )
            with c3:
                filter_assignee = st.text_input("담당자 검색")

            q = db.query(ActionItem)
            if filter_status != "전체":
                q = q.filter(ActionItem.status == filter_status)
            if filter_company_a:
                q = q.filter(ActionItem.company_id == filter_company_a.id)
            if filter_assignee:
                q = q.filter(ActionItem.assignee.ilike(f"%{filter_assignee}%"))

            items = q.order_by(ActionItem.due_date).all()
            st.caption(f"총 {len(items)}건")

            for ai in items:
                is_overdue = ai.due_date and ai.due_date < date.today() and ai.status not in ["완료"]
                border_color = "#EF4444" if is_overdue else "#1E40AF"

                with st.container():
                    cols = st.columns([4, 1, 1, 1])
                    with cols[0]:
                        st.markdown(
                            f'<div style="border-left:3px solid {border_color};padding-left:8px;">'
                            f'{status_badge(ai.status)} <b>{ai.content}</b><br>'
                            f'<small style="color:#64748B">'
                            f'[{ai.company.name}] 담당: {ai.assignee or "-"} | 기한: {fmt_date(ai.due_date)}'
                            f'{"⚠️ 기한초과" if is_overdue else ""}</small></div>',
                            unsafe_allow_html=True,
                        )
                    with cols[1]:
                        new_status = st.selectbox(
                            "", ACTION_STATUSES,
                            index=ACTION_STATUSES.index(ai.status),
                            key=f"ai_s_{ai.id}", label_visibility="collapsed"
                        )
                        if new_status != ai.status:
                            ai.status = new_status
                            db.commit()
                            st.rerun()
                    with cols[2]:
                        new_due = st.date_input("", value=ai.due_date or date.today(),
                            key=f"ai_d_{ai.id}", label_visibility="collapsed")
                        if new_due != ai.due_date:
                            ai.due_date = new_due
                            db.commit()
                    with cols[3]:
                        if st.button("🗑️", key=f"ai_del_{ai.id}"):
                            db.delete(ai)
                            db.commit()
                            st.rerun()
                    st.divider()

            # 수동 추가
            with st.expander("➕ 액션아이템 추가"):
                with st.form("add_action_manual", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        company_sel = st.selectbox("고객사 *", companies_all, format_func=lambda x: x.name, key="am_company")
                        content = st.text_area("내용 *")
                    with c2:
                        assignee = st.text_input("담당자")
                        due_date = st.date_input("기한", value=date.today() + timedelta(days=7))
                        notes = st.text_input("메모")
                    if st.form_submit_button("추가"):
                        if not content:
                            st.error("내용을 입력해주세요.")
                        else:
                            db.add(ActionItem(
                                company_id=company_sel.id, content=content,
                                assignee=assignee or None, due_date=due_date, notes=notes or None,
                            ))
                            db.commit()
                            st.toast("추가되었습니다.", icon="✅")
                            st.rerun()

        # ── 약속사항 ──
        with tab_promise:
            c1, c2 = st.columns(2)
            with c1:
                filter_ps = st.selectbox("상태 필터", ["전체"] + PROMISE_STATUSES)
            with c2:
                companies_all2 = db.query(Company).options(
                joinedload(Company.contacts),
                joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
                joinedload(Company.promises),
                joinedload(Company.action_items),
                joinedload(Company.customer_infos),
            ).order_by(Company.name).all()
                filter_pc = st.selectbox(
                    "고객사 필터", [None] + companies_all2,
                    format_func=lambda x: x.name if x else "전체", key="fp_company"
                )

            q2 = db.query(Promise)
            if filter_ps != "전체":
                q2 = q2.filter(Promise.status == filter_ps)
            if filter_pc:
                q2 = q2.filter(Promise.company_id == filter_pc.id)

            promises = q2.order_by(Promise.due_date).all()
            st.caption(f"총 {len(promises)}건")

            for p in promises:
                is_overdue = p.due_date and p.due_date < date.today() and p.status not in ["완료"]
                border_color = "#EF4444" if p.status == "불이행" else ("#F59E0B" if is_overdue else "#1E40AF")

                with st.container():
                    cols = st.columns([4, 1, 1])
                    with cols[0]:
                        st.markdown(
                            f'<div style="border-left:3px solid {border_color};padding-left:8px;">'
                            f'{status_badge(p.status)} <b>{p.content}</b><br>'
                            f'<small style="color:#64748B">'
                            f'[{p.company.name}] 약속자: {p.promised_by or "-"} | '
                            f'약속일: {fmt_date(p.promised_date)} | 기한: {fmt_date(p.due_date)}'
                            f'{"⚠️ 기한초과" if is_overdue else ""}</small></div>',
                            unsafe_allow_html=True,
                        )
                    with cols[1]:
                        new_ps = st.selectbox(
                            "", PROMISE_STATUSES,
                            index=PROMISE_STATUSES.index(p.status),
                            key=f"p_s_{p.id}", label_visibility="collapsed"
                        )
                        if new_ps != p.status:
                            p.status = new_ps
                            p.updated_at = datetime.now()
                            db.commit()
                            st.rerun()
                    with cols[2]:
                        if st.button("🗑️", key=f"p_del_{p.id}"):
                            db.delete(p)
                            db.commit()
                            st.rerun()
                    st.divider()

            # 수동 약속 추가
            with st.expander("➕ 약속사항 추가"):
                with st.form("add_promise_manual", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        pc_sel = st.selectbox("고객사 *", companies_all2, format_func=lambda x: x.name, key="pm_company")
                        pm_content = st.text_area("약속 내용 *")
                        pm_by = st.text_input("약속한 사람")
                    with c2:
                        pm_date = st.date_input("약속일", value=date.today())
                        pm_due  = st.date_input("이행 예정일", value=date.today() + timedelta(days=14))
                        pm_notes = st.text_input("메모")
                    if st.form_submit_button("추가"):
                        if not pm_content:
                            st.error("약속 내용을 입력해주세요.")
                        else:
                            db.add(Promise(
                                company_id=pc_sel.id, content=pm_content,
                                promised_by=pm_by or None,
                                promised_date=pm_date, due_date=pm_due,
                                notes=pm_notes or None,
                            ))
                            db.commit()
                            st.toast("추가되었습니다.", icon="✅")
                            st.rerun()

    finally:
        db.close()


# ─── 리스크 분석 ───────────────────────────────────────────────────────────────

def page_risk_analysis():
    st.title("⚠️ 리스크 분석")

    db = get_db()
    try:
        companies = db.query(Company).options(
                joinedload(Company.contacts),
                joinedload(Company.meetings).joinedload(MeetingRecord.analysis),
                joinedload(Company.promises),
                joinedload(Company.action_items),
                joinedload(Company.customer_infos),
            ).order_by(Company.name).all()
        if not companies:
            st.info("고객사를 먼저 등록해주세요.")
            return

        # 전체 리스크 스코어보드
        st.subheader("📊 고객사별 리스크 스코어보드")

        rows = []
        for c in companies:
            # 약속 불이행 횟수
            breach = sum(1 for p in c.promises if p.status == "불이행")
            # 지연 약속 수
            delayed_p = sum(1 for p in c.promises if p.status == "지연")
            # 기한 초과 액션
            overdue_a = sum(1 for a in c.action_items
                           if a.due_date and a.due_date < date.today() and a.status not in ["완료"])
            # AI 분석 평균 위험도
            risk_scores = [m.analysis.risk_score for m in c.meetings if m.analysis]
            avg_risk = round(sum(risk_scores) / len(risk_scores)) if risk_scores else 0
            avg_trust = round(sum(
                m.analysis.trust_score for m in c.meetings if m.analysis
            ) / len(risk_scores)) if risk_scores else 0

            # 종합 리스크 계산
            composite = min(100, breach * 20 + delayed_p * 10 + overdue_a * 5 + avg_risk * 0.5)

            rows.append({
                "고객사": c.name,
                "사업구분": c.business_type or "-",
                "영업단계": c.sales_stage or "-",
                "약속불이행": breach,
                "약속지연": delayed_p,
                "액션지연": overdue_a,
                "AI평균위험": avg_risk,
                "AI평균신뢰": avg_trust,
                "종합리스크": int(composite),
                "리스크등급": c.risk_level or "-",
            })

        df = pd.DataFrame(rows).sort_values("종합리스크", ascending=False)

        # 색상 적용
        def color_risk(val):
            if isinstance(val, int):
                if val >= 70:
                    return "background-color: #FEE2E2"
                elif val >= 40:
                    return "background-color: #FEF3C7"
                else:
                    return "background-color: #D1FAE5"
            return ""

        st.dataframe(
            df.style.applymap(color_risk, subset=["종합리스크", "AI평균위험"]),
            hide_index=True, use_container_width=True
        )

        st.divider()

        # 개별 고객사 상세 리스크
        st.subheader("🔍 고객사별 상세 분석")
        sel = st.selectbox("고객사 선택", companies, format_func=lambda x: x.name, key="risk_sel")

        # 리스크 요인 수집
        risk_factors_all = []
        complaints_all = []
        competitor_all = []
        for m in sel.meetings:
            if m.analysis:
                risk_factors_all.extend(m.analysis.risk_factors or [])
                complaints_all.extend(m.analysis.complaints or [])
                competitor_all.extend(m.analysis.competitor_mentions or [])

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**누적 리스크 요인**")
            if risk_factors_all:
                for rf in risk_factors_all:
                    st.write(f"🔴 {rf}")
            else:
                st.write("없음")

            st.markdown("**누적 불만·우려사항**")
            if complaints_all:
                for comp in complaints_all:
                    st.write(f"⚠️ {comp}")
            else:
                st.write("없음")

        with c2:
            st.markdown("**경쟁사 언급 내역**")
            if competitor_all:
                for comp in competitor_all:
                    st.write(f"🔵 {comp}")
            else:
                st.write("없음")

            st.markdown("**불이행 약속사항**")
            breaches = [p for p in sel.promises if p.status == "불이행"]
            if breaches:
                for b in breaches:
                    st.write(f"❌ {b.content} (기한: {fmt_date(b.due_date)})")
            else:
                st.success("약속 불이행 없음")

        # 위험도 추이 (미팅별)
        if sel.meetings:
            risk_trend = [
                {"날짜": str(m.meeting_date), "위험도": m.analysis.risk_score, "신뢰도": m.analysis.trust_score}
                for m in sorted(sel.meetings, key=lambda m: m.meeting_date or date.min)
                if m.analysis
            ]
            if risk_trend:
                st.markdown("**위험도·신뢰도 추이**")
                df_trend = pd.DataFrame(risk_trend).set_index("날짜")
                st.line_chart(df_trend, use_container_width=True)

        # 리스크 등급 수동 업데이트
        st.divider()
        new_risk = st.selectbox("리스크 등급 업데이트", IMPORTANCE,
            index=IMPORTANCE.index(sel.risk_level) if sel.risk_level in IMPORTANCE else 1)
        if st.button("리스크 등급 저장"):
            sel.risk_level = new_risk
            sel.updated_at = datetime.now()
            db.commit()
            st.toast("저장되었습니다.", icon="✅")
            st.rerun()

    finally:
        db.close()


# ─── 검색 ────────────────────────────────────────────────────────────────────

def page_search():
    st.title("🔍 통합 검색")

    query = st.text_input("검색어 입력", placeholder="고객사명, 담당자, 경쟁사, 제품명, 미팅 내용 등")

    if not query:
        st.info("검색어를 입력하면 전체 데이터에서 검색합니다.")
        return

    db = get_db()
    try:
        # 고객사 검색
        companies = db.query(Company).filter(
            or_(Company.name.ilike(f"%{query}%"), Company.memo.ilike(f"%{query}%"))
        ).all()

        # 담당자 검색
        contacts = db.query(Contact).filter(
            or_(Contact.name.ilike(f"%{query}%"), Contact.position.ilike(f"%{query}%"))
        ).all()

        # 미팅 내용 검색 (원문 + 분석)
        meetings = db.query(MeetingRecord).filter(
            MeetingRecord.raw_text.ilike(f"%{query}%")
        ).limit(20).all()

        analyses_q = db.query(MeetingAnalysis).filter(
            or_(
                MeetingAnalysis.one_line_summary.ilike(f"%{query}%"),
                MeetingAnalysis.detailed_summary.ilike(f"%{query}%"),
            )
        ).limit(10).all()

        # 약속사항 검색
        promises = db.query(Promise).filter(Promise.content.ilike(f"%{query}%")).all()

        # 액션아이템 검색
        actions = db.query(ActionItem).filter(ActionItem.content.ilike(f"%{query}%")).all()

        st.divider()

        if companies:
            st.subheader(f"🏢 고객사 ({len(companies)}건)")
            for c in companies:
                st.write(f"• **{c.name}** | {c.business_type or '-'} | {c.sales_stage or '-'}")

        if contacts:
            st.subheader(f"👤 담당자 ({len(contacts)}건)")
            for ct in contacts:
                st.write(f"• **{ct.name}** ({ct.position or '-'}) – {ct.company.name}")

        if meetings:
            st.subheader(f"📝 미팅 원문 ({len(meetings)}건)")
            for m in meetings:
                idx = m.raw_text.lower().find(query.lower())
                snippet = m.raw_text[max(0, idx-50):idx+100] if idx >= 0 else m.raw_text[:100]
                st.write(f"• **{fmt_date(m.meeting_date)}** [{m.company.name}] …{snippet}…")

        if analyses_q:
            st.subheader(f"🤖 AI 분석 결과 ({len(analyses_q)}건)")
            for a in analyses_q:
                st.write(f"• **{fmt_date(a.meeting.meeting_date)}** [{a.meeting.company.name}] {a.one_line_summary or ''}")

        if promises:
            st.subheader(f"🤝 약속사항 ({len(promises)}건)")
            for p in promises:
                st.markdown(f"• {status_badge(p.status)} [{p.company.name}] {p.content}", unsafe_allow_html=True)

        if actions:
            st.subheader(f"✅ 액션아이템 ({len(actions)}건)")
            for a in actions:
                st.markdown(f"• {status_badge(a.status)} [{a.company.name}] {a.content}", unsafe_allow_html=True)

        total = len(companies) + len(contacts) + len(meetings) + len(analyses_q) + len(promises) + len(actions)
        if total == 0:
            st.warning("검색 결과가 없습니다.")

    finally:
        db.close()


# ─── 일정 관리 ───────────────────────────────────────────────────────────────

REMIND_OPTIONS = {
    "30분 전": 30,
    "1시간 전": 60,
    "3시간 전": 180,
    "하루 전": 1440,
    "2일 전": 2880,
}
EVENT_COLORS = {
    "파랑": "#1E40AF",
    "초록": "#059669",
    "빨강": "#DC2626",
    "주황": "#D97706",
    "보라": "#7C3AED",
    "회색": "#64748B",
}


def _save_schedule(db, title, description, start_dt, end_dt, all_day,
                   color, company_id, remind_enabled, remind_minutes,
                   schedule_id=None):
    if schedule_id:
        s = db.get(Schedule, schedule_id)
        if s:
            s.title = title; s.description = description
            s.start_dt = start_dt; s.end_dt = end_dt; s.all_day = all_day
            s.color = color; s.company_id = company_id
            s.remind_enabled = remind_enabled; s.remind_minutes = remind_minutes
            s.remind_sent = False
    else:
        db.add(Schedule(
            title=title, description=description, start_dt=start_dt,
            end_dt=end_dt, all_day=all_day, color=color,
            company_id=company_id, remind_enabled=remind_enabled,
            remind_minutes=remind_minutes,
        ))
    db.commit()


def _schedule_form(db, companies_all, form_key, default_date=None,
                   editing: Schedule = None):
    """공통 일정 입력 폼. 저장 성공 시 True 반환."""
    now = datetime.now()
    default_start = date.fromisoformat(default_date) if default_date else date.today()
    default_hour = now.hour if now.hour < 23 else 22

    with st.form(form_key, clear_on_submit=True):
        title = st.text_input("제목 *", value=editing.title if editing else "")
        description = st.text_area("내용/메모", value=editing.description or "" if editing else "")

        c1, c2 = st.columns(2)
        with c1:
            all_day = st.checkbox("종일 일정", value=editing.all_day if editing else False)
            start_date = st.date_input("시작 날짜", value=editing.start_dt.date() if editing else default_start)
            if not all_day:
                start_time = st.time_input("시작 시간",
                    value=editing.start_dt.time() if editing else now.replace(hour=default_hour, minute=0, second=0).time())
        with c2:
            color_names = list(EVENT_COLORS.keys())
            color_vals  = list(EVENT_COLORS.values())
            cur_color_idx = color_vals.index(editing.color) if editing and editing.color in color_vals else 0
            color_label = st.selectbox("색상", color_names, index=cur_color_idx)
            end_date = st.date_input("종료 날짜", value=editing.end_dt.date() if editing else default_start)
            if not all_day:
                end_h = min(default_hour + 1, 23)
                end_time = st.time_input("종료 시간",
                    value=editing.end_dt.time() if editing else now.replace(hour=end_h, minute=0, second=0).time())

        company_opts = [None] + companies_all
        cur_co_idx = next((i+1 for i, c in enumerate(companies_all) if editing and c.id == editing.company_id), 0)
        linked_company = st.selectbox("고객사 연결 (선택)", company_opts,
            index=cur_co_idx, format_func=lambda x: x.name if x else "없음")

        st.divider()
        col_r1, col_r2 = st.columns(2)
        remind_enabled = col_r1.checkbox("텔레그램 알림", value=editing.remind_enabled if editing else True)
        remind_opts = list(REMIND_OPTIONS.keys())
        cur_remind = next((k for k, v in REMIND_OPTIONS.items() if editing and v == editing.remind_minutes), "하루 전")
        remind_label = col_r2.selectbox("알림 시간", remind_opts,
            index=remind_opts.index(cur_remind), disabled=not remind_enabled)

        label = "💾 수정 저장" if editing else "💾 일정 저장"
        if st.form_submit_button(label, type="primary"):
            if not title:
                st.error("제목은 필수입니다.")
                return False
            start_dt = datetime.combine(start_date, start_time if not all_day else datetime.min.time())
            end_dt   = datetime.combine(end_date,   end_time   if not all_day else datetime.min.time())
            _save_schedule(db, title, description or None, start_dt, end_dt, all_day,
                           EVENT_COLORS[color_label],
                           linked_company.id if linked_company else None,
                           remind_enabled, REMIND_OPTIONS[remind_label],
                           schedule_id=editing.id if editing else None)
            return True
    return False


def page_calendar():
    from streamlit_calendar import calendar as st_calendar
    from services.telegram_service import check_and_send_reminders, send_message, _get_token, _get_chat_id
    from database.models import Schedule

    st.title("🗓️ 일정 관리")

    db = get_db()
    try:
        # ── 알림 자동 체크 (60초에 한 번만 실행) ──
        @st.cache_data(ttl=60, show_spinner=False)
        def _check_reminders_cached(_tick):
            return check_and_send_reminders(db)

        if _get_token() and _get_chat_id():
            import time as _time
            tick = int(_time.time() // 60)
            sent = _check_reminders_cached(tick)
            if sent:
                st.toast(f"텔레그램 알림 {sent}건 전송됨", icon="📨")

        companies_all = db.query(Company).order_by(Company.name).all()

        tab_cal, tab_list, tab_settings = st.tabs(
            ["📅 캘린더", "📋 일정 목록", "⚙️ 텔레그램 설정"]
        )

        # ── 캘린더 뷰 ──
        with tab_cal:
            # ── 년/월 드롭다운 네비게이터 ──
            now = datetime.now()
            nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 4])
            nav_year  = nav_col1.selectbox("년도", list(range(now.year - 2, now.year + 5)),
                                           index=2, key="cal_nav_year", label_visibility="collapsed")
            nav_month = nav_col2.selectbox("월", list(range(1, 13)),
                                           index=now.month - 1, key="cal_nav_month", label_visibility="collapsed",
                                           format_func=lambda m: f"{m}월")
            initial_date = f"{nav_year}-{nav_month:02d}-01"

            schedules = db.query(Schedule).options(
                joinedload(Schedule.company)
            ).all()

            events = []
            for s in schedules:
                ev = {
                    "id": str(s.id),
                    "title": s.title,
                    "color": s.color or "#1E40AF",
                    "allDay": s.all_day,
                    "extendedProps": {"company": s.company.name if s.company else ""},
                }
                if s.all_day:
                    ev["start"] = s.start_dt.strftime("%Y-%m-%d")
                    # FullCalendar all-day end는 exclusive → +1일
                    ev["end"] = (s.end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
                else:
                    ev["start"] = s.start_dt.strftime("%Y-%m-%dT%H:%M:%S")
                    ev["end"]   = s.end_dt.strftime("%Y-%m-%dT%H:%M:%S")
                if s.company:
                    ev["title"] = f"[{s.company.name}] {s.title}"
                events.append(ev)

            calendar_options = {
                "initialView": "dayGridMonth",
                "initialDate": initial_date,
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,timeGridWeek,timeGridDay,listWeek",
                },
                "locale": "ko",
                "height": 620,
                "selectable": True,
                "selectMirror": True,
                "editable": False,
                "nowIndicator": True,
                "dayMaxEvents": 3,
                "businessHours": {"daysOfWeek": [1,2,3,4,5]},
            }
            custom_css = """
                .fc-event { cursor: pointer; border-radius: 4px; font-size: 0.82rem; padding: 1px 3px; }
                .fc-toolbar-title { font-size: 1.2rem !important; }
                .fc-today { background: #EFF6FF !important; }
                .fc-daygrid-day:hover { background: #F1F5F9; cursor: pointer; }
                .fc-now-indicator { border-color: #DC2626; }
            """
            result = st_calendar(events=events, options=calendar_options,
                                 custom_css=custom_css, key="main_cal")

            # ── 캘린더 이벤트 처리 ──
            if result and result.get("dateClick"):
                st.session_state["cal_day"] = result["dateClick"]["date"][:10]
                st.session_state.pop("cal_detail_id", None)
                st.session_state.pop("cal_add_mode", None)
                st.session_state.pop("cal_show_edit_form", None)

            if result and result.get("eventClick"):
                ev_id = int(result["eventClick"]["event"]["id"])
                # 해당 이벤트의 날짜도 함께 저장 (뒤로가기용)
                ev_date = result["eventClick"]["event"]["start"][:10]
                st.session_state["cal_day"] = ev_date
                st.session_state["cal_detail_id"] = ev_id
                st.session_state.pop("cal_add_mode", None)
                st.session_state.pop("cal_show_edit_form", None)

            if result and result.get("select"):
                st.session_state["cal_day"] = result["select"]["start"][:10]
                st.session_state["cal_add_mode"] = True
                st.session_state.pop("cal_detail_id", None)
                st.session_state.pop("cal_show_edit_form", None)

            st.divider()

            cal_day       = st.session_state.get("cal_day")
            cal_detail_id = st.session_state.get("cal_detail_id")
            cal_add_mode  = st.session_state.get("cal_add_mode", False)

            # ══════════════════════════════════════════════
            # LEVEL 3 : 일정 상세 / 수정
            # ══════════════════════════════════════════════
            if cal_detail_id:
                sel = db.get(Schedule, cal_detail_id)
                if sel:
                    # 헤더: 뒤로가기 + 제목
                    h_col1, h_col2 = st.columns([1, 6])
                    if h_col1.button("← 뒤로", key="back_to_day"):
                        st.session_state.pop("cal_detail_id", None)
                        st.session_state.pop("cal_show_edit_form", None)
                        st.rerun()

                    # 일정 상세 카드
                    date_str  = sel.start_dt.strftime("%Y년 %m월 %d일 (%a)")
                    start_str = sel.start_dt.strftime("%H:%M") if not sel.all_day else "종일"
                    end_str   = sel.end_dt.strftime("%H:%M")   if not sel.all_day else ""

                    st.markdown(f"""
<div style="background:#F8FAFC;border-radius:12px;padding:20px 24px;border:1px solid #E2E8F0;margin-bottom:12px;">
  <div style="font-size:1.4rem;font-weight:700;color:#1E40AF;margin-bottom:8px;">{sel.title}</div>
  <div style="color:#64748B;font-size:0.9rem;margin-bottom:12px;">{date_str}</div>
  <div style="font-size:1.1rem;font-weight:600;color:#0F172A;">
    {"종일" if sel.all_day else f"🕐 {start_str} → {end_str}"}
  </div>
  {"<div style='margin-top:8px;color:#475569;'>🏢 " + sel.company.name + "</div>" if sel.company else ""}
  {"<div style='margin-top:8px;color:#475569;'>📝 " + sel.description + "</div>" if sel.description else ""}
</div>
""", unsafe_allow_html=True)

                    remind_lbl = next((k for k, v in REMIND_OPTIONS.items() if v == sel.remind_minutes), f"{sel.remind_minutes}분 전")
                    st.markdown(f"🔔 알림: **{'✅ ' + remind_lbl if sel.remind_enabled else '❌ 꺼짐'}**")
                    if sel.remind_sent:
                        st.caption("(알림 전송 완료)")

                    st.markdown("---")
                    col_edit, col_del = st.columns(2)
                    if col_edit.button("✏️ 수정", key="btn_detail_edit", use_container_width=True):
                        st.session_state["cal_show_edit_form"] = True
                    if col_del.button("🗑️ 삭제", key="btn_detail_del",
                                      type="primary", use_container_width=True):
                        db.delete(sel)
                        db.commit()
                        st.session_state.pop("cal_detail_id", None)
                        st.session_state.pop("cal_show_edit_form", None)
                        st.toast("삭제되었습니다.", icon="🗑️")
                        st.rerun()

                    if st.session_state.get("cal_show_edit_form"):
                        st.markdown("#### ✏️ 일정 수정")
                        if _schedule_form(db, companies_all, "edit_ev_form", editing=sel):
                            st.session_state.pop("cal_detail_id", None)
                            st.session_state.pop("cal_show_edit_form", None)
                            st.toast("수정되었습니다.", icon="✅")
                            st.rerun()

            # ══════════════════════════════════════════════
            # LEVEL 2 : 날짜별 일정 목록
            # ══════════════════════════════════════════════
            elif cal_day:
                try:
                    day_dt = datetime.strptime(cal_day, "%Y-%m-%d")
                except ValueError:
                    day_dt = datetime.now()

                # 헤더
                weekday_ko = ["월", "화", "수", "목", "금", "토", "일"]
                day_label  = f"{day_dt.year}년 {day_dt.month}월 {day_dt.day}일 ({weekday_ko[day_dt.weekday()]})"
                hc1, hc2, hc3 = st.columns([1, 5, 1])
                if hc1.button("← 캘린더", key="back_to_cal"):
                    st.session_state.pop("cal_day", None)
                    st.rerun()
                hc2.markdown(f"### {day_label}")
                if hc3.button("＋ 추가", key="btn_day_add"):
                    st.session_state["cal_add_mode"] = True
                    st.rerun()

                # 해당 날짜의 일정 조회
                day_start = day_dt.replace(hour=0,  minute=0,  second=0)
                day_end   = day_dt.replace(hour=23, minute=59, second=59)
                day_scheds = (
                    db.query(Schedule)
                    .options(joinedload(Schedule.company))
                    .filter(Schedule.start_dt <= day_end, Schedule.end_dt >= day_start)
                    .order_by(Schedule.all_day.desc(), Schedule.start_dt)
                    .all()
                )

                if not day_scheds:
                    st.info("이 날 등록된 일정이 없습니다.")
                else:
                    for s in day_scheds:
                        if s.all_day:
                            time_label = "종일"
                            time_end   = ""
                        else:
                            time_label = s.start_dt.strftime("%H:%M")
                            time_end   = s.end_dt.strftime("%H:%M")

                        bar_color = s.color or "#1E40AF"
                        company_badge = f"<span style='background:{bar_color};color:#fff;border-radius:4px;padding:1px 6px;font-size:0.75rem;'>{s.company.name}</span>" if s.company else ""

                        clicked_item = st.button(
                            f"{'종일  ' if s.all_day else f'{time_label} → {time_end}  '}  {s.title}",
                            key=f"day_item_{s.id}",
                            use_container_width=True,
                        )
                        if clicked_item:
                            st.session_state["cal_detail_id"] = s.id
                            st.session_state.pop("cal_add_mode", None)
                            st.rerun()

                # 일정 추가 폼 (＋ 추가 버튼 눌렀을 때)
                if cal_add_mode:
                    st.markdown("---")
                    st.markdown(f"#### ➕ {day_label} 일정 추가")
                    if _schedule_form(db, companies_all, "day_add_form", default_date=cal_day):
                        st.session_state.pop("cal_add_mode", None)
                        st.toast("일정이 저장되었습니다.", icon="✅")
                        st.rerun()
                    if st.button("✕ 취소", key="cancel_day_add"):
                        st.session_state.pop("cal_add_mode", None)
                        st.rerun()

            # ══════════════════════════════════════════════
            # LEVEL 1 : 기본 안내
            # ══════════════════════════════════════════════
            else:
                st.caption("💡 캘린더에서 날짜를 클릭하면 해당 날의 일정을 확인할 수 있습니다.")

        # ── 일정 목록 ──
        with tab_list:
            col_f1, col_f2 = st.columns(2)
            filter_upcoming = col_f1.checkbox("앞으로의 일정만", value=True)
            filter_company  = col_f2.selectbox("고객사 필터", [None] + companies_all,
                format_func=lambda x: x.name if x else "전체")

            q = db.query(Schedule).options(joinedload(Schedule.company))
            if filter_upcoming:
                q = q.filter(Schedule.start_dt >= datetime.now())
            if filter_company:
                q = q.filter(Schedule.company_id == filter_company.id)
            schedules_all = q.order_by(Schedule.start_dt).all()

            if not schedules_all:
                st.info("일정이 없습니다.")
            else:
                for s in schedules_all:
                    passed = s.start_dt < datetime.now()
                    time_str = s.start_dt.strftime("%Y-%m-%d %H:%M") if not s.all_day else s.start_dt.strftime("%Y-%m-%d (종일)")
                    badge = "🔴" if passed else "🟢"
                    with st.expander(f"{badge} {time_str} | **{s.title}**"):
                        c1, c2, c3 = st.columns(3)
                        c1.write(f"**시작:** {time_str}")
                        c2.write(f"**종료:** {s.end_dt.strftime('%Y-%m-%d %H:%M') if not s.all_day else s.end_dt.strftime('%Y-%m-%d')}")
                        c3.write(f"**고객사:** {s.company.name if s.company else '-'}")
                        if s.description:
                            st.write(f"**내용:** {s.description}")
                        remind_lbl = next((k for k, v in REMIND_OPTIONS.items() if v == s.remind_minutes), f"{s.remind_minutes}분 전")
                        st.write(f"**알림:** {'✅ ' + remind_lbl if s.remind_enabled else '❌ 꺼짐'} {'(전송완료)' if s.remind_sent else ''}")
                        col_d1, col_d2 = st.columns([1, 4])
                        if col_d1.button("🗑️ 삭제", key=f"del_sched_{s.id}"):
                            to_del = db.get(Schedule, s.id)
                            if to_del:
                                db.delete(to_del)
                                db.commit()
                                st.toast("삭제되었습니다.", icon="🗑️")
                                st.rerun()

        # ── 텔레그램 설정 ──
        with tab_settings:
            st.subheader("⚙️ 텔레그램 알림 설정")

            token = _get_token()
            chat_id = _get_chat_id()

            if token and chat_id:
                st.success(f"✅ 텔레그램 연동 완료 (Chat ID: {chat_id})")
            else:
                st.warning("텔레그램이 연동되지 않았습니다.")

            st.divider()
            st.markdown("""
### 설정 방법

1. **봇 생성**: 텔레그램에서 [@BotFather](https://t.me/BotFather) 검색 → `/newbot` → 봇 이름 설정 → **Token** 복사

2. **Chat ID 확인**:
   - 생성한 봇에게 아무 메시지 전송
   - 브라우저에서 아래 URL 접속 (토큰 교체):
     ```
     https://api.telegram.org/bot[YOUR_TOKEN]/getUpdates
     ```
   - 결과에서 `"id"` 값이 Chat ID

3. **Streamlit Secrets에 추가**:
   ```toml
   TELEGRAM_BOT_TOKEN = "1234567890:ABCdef..."
   TELEGRAM_CHAT_ID = "123456789"
   ```

4. 앱 재시작 후 아래 버튼으로 테스트
""")

            if st.button("📨 테스트 메시지 전송"):
                if not token:
                    st.error("TELEGRAM_BOT_TOKEN이 Secrets에 없습니다.")
                elif not chat_id:
                    st.error("TELEGRAM_CHAT_ID가 Secrets에 없습니다.")
                else:
                    ok = send_message("✅ Sales Intelligence 알림 테스트 메시지입니다!")
                    if ok:
                        st.toast("테스트 메시지 전송 성공!", icon="📨")
                    else:
                        st.error("전송 실패. Token 또는 Chat ID를 확인해주세요.")

    finally:
        db.close()


# ─── 메인 ────────────────────────────────────────────────────────────────────

PAGES = {
    "🏠 대시보드":          page_dashboard,
    "🏢 고객사 관리":        page_company_management,
    "📤 미팅 기록 업로드":   page_meeting_upload,
    "📋 미팅 요약 결과":     page_meeting_results,
    "📅 고객사별 타임라인":   page_timeline,
    "✅ 액션아이템 관리":     page_action_items,
    "⚠️ 리스크 분석":        page_risk_analysis,
    "🔍 통합 검색":           page_search,
    "🗓️ 일정 관리":           page_calendar,
}

with st.sidebar:
    # 로고
    st.markdown("""
    <div style="padding:1.5rem 1rem 1rem;border-bottom:1px solid #1E293B;margin-bottom:0.5rem;">
        <div style="font-size:2rem;line-height:1;margin-bottom:0.4rem;">🎯</div>
        <div style="color:#F8FAFC;font-size:1.05rem;font-weight:700;letter-spacing:-0.3px;">Sales Intelligence</div>
        <div style="color:#64748B;font-size:0.72rem;margin-top:2px;">영업 관리 시스템</div>
    </div>
    """, unsafe_allow_html=True)

    menu_items = list(PAGES.keys())
    if "selected_menu" not in st.session_state:
        st.session_state["selected_menu"] = menu_items[0]

    # 메뉴 버튼 — 선택된 항목은 HTML로 강조
    st.markdown("<div style='padding:0.3rem 0;'>", unsafe_allow_html=True)
    for item in menu_items:
        is_active = st.session_state["selected_menu"] == item
        if is_active:
            # 선택된 항목: 파란 하이라이트 표시 후 버튼
            st.markdown(
                f'<div style="background:#1D4ED8;border-radius:8px;margin:1px 8px;">'
                f'<p style="color:#FFFFFF;font-weight:700;font-size:0.88rem;'
                f'padding:0.5rem 0.8rem;margin:0;pointer-events:none;">{item}</p></div>',
                unsafe_allow_html=True,
            )
        else:
            if st.button(item, key=f"menu_{item}", use_container_width=True):
                st.session_state["selected_menu"] = item
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    selected = st.session_state["selected_menu"]

    st.markdown("""
    <div style="position:absolute;bottom:1rem;left:0;right:0;text-align:center;">
        <span style="color:#334155;font-size:0.7rem;">Powered by Claude AI</span>
    </div>
    """, unsafe_allow_html=True)

PAGES[selected]()
