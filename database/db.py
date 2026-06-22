import os
from pathlib import Path
from urllib.parse import urlparse, unquote

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database.models import Base


def _get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    db_path = Path(__file__).parent.parent / "data" / "sales_intelligence.db"
    db_path.parent.mkdir(exist_ok=True)
    return f"sqlite:///{db_path}"


def _build_engine():
    raw_url = _get_database_url()

    # normalize postgres:// → postgresql://
    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    if raw_url.startswith("sqlite"):
        return create_engine(raw_url, connect_args={"check_same_thread": False})

    # PostgreSQL: parse URL manually to handle special chars in password
    parsed = urlparse(raw_url)
    username = parsed.username or ""
    password = unquote(parsed.password or "")
    host = parsed.hostname or ""
    port = parsed.port or 5432
    database = (parsed.path or "/postgres").lstrip("/")

    from sqlalchemy.engine import URL as SAURL
    sa_url = SAURL.create(
        drivername="postgresql+pg8000",
        username=username,
        password=password,
        host=host,
        port=port,
        database=database,
    )

    return create_engine(
        sa_url,
        connect_args={"ssl_context": True},
        pool_pre_ping=True,
        pool_recycle=300,
    )


_engine = _build_engine()

SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def create_database() -> None:
    Base.metadata.create_all(_engine)
