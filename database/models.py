from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    ForeignKey, Integer, JSON, String, Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    start_dt = Column(DateTime, nullable=False)
    end_dt = Column(DateTime, nullable=False)
    all_day = Column(Boolean, default=False)
    color = Column(String(20), default="#1E40AF")
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    remind_enabled = Column(Boolean, default=True)
    remind_minutes = Column(Integer, default=1440)   # 기본 1일 전(1440분)
    remind_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    company = relationship("Company", backref="schedules")


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    business_type = Column(String(50))       # CSO / TLD / 기타
    industry = Column(String(100))
    address = Column(Text)
    website = Column(String(200))
    sales_stage = Column(String(100))        # 잠재/접촉/제안/협상/계약/완료/보류
    expected_revenue = Column(Float)
    importance = Column(String(20))          # 높음/보통/낮음
    risk_level = Column(String(20))          # 높음/보통/낮음
    memo = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    contacts = relationship("Contact", back_populates="company", cascade="all, delete-orphan")
    meetings = relationship("MeetingRecord", back_populates="company", cascade="all, delete-orphan")
    promises = relationship("Promise", back_populates="company", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="company", cascade="all, delete-orphan")
    customer_infos = relationship("CustomerInfo", back_populates="company", cascade="all, delete-orphan")


class Contact(Base):
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    name = Column(String(100), nullable=False)
    position = Column(String(100))
    phone = Column(String(50))
    email = Column(String(200))
    birthday = Column(String(20))            # MM-DD 또는 YYYY-MM-DD
    is_primary = Column(Boolean, default=False)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    company = relationship("Company", back_populates="contacts")
    customer_infos = relationship("CustomerInfo", back_populates="contact", cascade="all, delete-orphan")


class CustomerInfo(Base):
    """고객 취향·중요 정보 (생일, 가족사항, 선호도 등)"""
    __tablename__ = "customer_infos"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    contact_id = Column(Integer, ForeignKey("contacts.id"), nullable=True)
    category = Column(String(100))           # 생일/취향/가족/주요이슈/기타
    key = Column(String(200))                # 항목명
    value = Column(Text)                     # 내용
    importance = Column(String(20), default="보통")  # 높음/보통/낮음
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    company = relationship("Company", back_populates="customer_infos")
    contact = relationship("Contact", back_populates="customer_infos")


class MeetingRecord(Base):
    __tablename__ = "meeting_records"

    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    meeting_date = Column(Date)
    meeting_type = Column(String(50))        # 방문/전화/온라인/기타
    attendees = Column(Text)
    raw_text = Column(Text)
    file_name = Column(String(200))
    memo = Column(Text)
    created_at = Column(DateTime, default=datetime.now)

    company = relationship("Company", back_populates="meetings")
    analysis = relationship("MeetingAnalysis", back_populates="meeting", uselist=False, cascade="all, delete-orphan")
    promises = relationship("Promise", back_populates="meeting", cascade="all, delete-orphan")
    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")


class MeetingAnalysis(Base):
    __tablename__ = "meeting_analyses"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meeting_records.id"), nullable=False, unique=True)
    one_line_summary = Column(Text)
    detailed_summary = Column(Text)
    full_report = Column(Text)
    meeting_overview = Column(JSON)
    topic_discussions = Column(JSON)
    key_discussions = Column(JSON)
    decisions = Column(JSON)
    customer_needs = Column(JSON)
    complaints = Column(JSON)
    price_mentions = Column(JSON)
    competitor_mentions = Column(JSON)
    promises_raw = Column(JSON)
    follow_ups = Column(JSON)
    action_items_structured = Column(JSON)
    pending_items = Column(JSON)
    risk_factors = Column(JSON)
    risks_and_checks = Column(JSON)
    next_meeting_questions = Column(JSON)
    sales_opportunities = Column(JSON)
    relationship_notes = Column(JSON)
    schedule_candidates = Column(JSON)
    trust_score = Column(Integer)
    risk_score = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)

    meeting = relationship("MeetingRecord", back_populates="analysis")


class Promise(Base):
    __tablename__ = "promises"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meeting_records.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    content = Column(Text, nullable=False)
    promised_by = Column(String(100))
    promised_date = Column(Date)
    due_date = Column(Date)
    status = Column(String(50), default="미확인")  # 미확인/진행중/완료/지연/불이행
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    meeting = relationship("MeetingRecord", back_populates="promises")
    company = relationship("Company", back_populates="promises")


class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True)
    meeting_id = Column(Integer, ForeignKey("meeting_records.id"), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    content = Column(Text, nullable=False)
    assignee = Column(String(100))
    due_date = Column(Date)
    status = Column(String(50), default="예정")  # 예정/진행중/완료/지연
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    meeting = relationship("MeetingRecord", back_populates="action_items")
    company = relationship("Company", back_populates="action_items")
