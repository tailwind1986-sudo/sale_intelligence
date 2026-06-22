import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    db_path = Path(__file__).parent.parent / "data" / "sales_intelligence.db"
    db_path.parent.mkdir(exist_ok=True)
    return f"sqlite:///{db_path}"


_DATABASE_URL = _get_database_url()

# postgres:// → postgresql:// 변환
if _DATABASE_URL.startswith("postgres://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgres://", "postgresql://", 1)

if _DATABASE_URL.startswith("sqlite"):
    # 로컬 SQLite
    _engine = create_engine(
        _DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
else:
    # PostgreSQL (Supabase) — pg8000 드라이버 사용 (Python 3.14 호환)
    # postgresql:// → postgresql+pg8000:// 변환
    pg_url = _DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)
    _engine = create_engine(
        pg_url,
        connect_args={"ssl_context": True},  # Supabase SSL 필수
        pool_pre_ping=True,
        pool_recycle=300,
    )

SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, expire_on_commit=False)


def create_database() -> None:
    Base.metadata.create_all(_engine)
