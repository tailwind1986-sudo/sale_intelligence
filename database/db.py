import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base


def _get_database_url() -> str:
    # 1순위: 환경변수 (Streamlit Cloud는 Secrets를 환경변수로 주입함)
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    # 2순위: 로컬 SQLite (개발용)
    db_path = Path(__file__).parent.parent / "data" / "sales_intelligence.db"
    db_path.parent.mkdir(exist_ok=True)
    return f"sqlite:///{db_path}"


_DATABASE_URL = _get_database_url()

# Heroku/Supabase 등에서 postgres:// 로 오는 경우 postgresql:// 로 변환
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if _DATABASE_URL.startswith("sqlite") else {}

_engine = create_engine(
    _DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,   # 연결 끊김 자동 감지
    pool_recycle=300,     # 5분마다 연결 갱신
)
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def create_database() -> None:
    Base.metadata.create_all(_engine)
