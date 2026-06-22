import os
from pathlib import Path

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base


def _get_database_url() -> str:
    # 1순위: Streamlit Cloud Secrets
    try:
        url = st.secrets.get("DATABASE_URL", "")
        if url:
            return url
    except Exception:
        pass
    # 2순위: 환경변수 (.env)
    url = os.getenv("DATABASE_URL", "")
    if url:
        return url
    # 3순위: 로컬 SQLite (개발용)
    db_path = Path(__file__).parent.parent / "data" / "sales_intelligence.db"
    db_path.parent.mkdir(exist_ok=True)
    return f"sqlite:///{db_path}"


_DATABASE_URL = _get_database_url()

# PostgreSQL이면 psycopg2 드라이버 명시
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {}

_engine = create_engine(_DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def create_database() -> None:
    Base.metadata.create_all(_engine)
