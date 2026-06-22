import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import URL as SA_URL
from sqlalchemy.orm import sessionmaker

from database.models import Base


def _get_raw_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if url:
        return url
    db_path = Path(__file__).parent.parent / "data" / "sales_intelligence.db"
    db_path.parent.mkdir(exist_ok=True)
    return f"sqlite:///{db_path}"


def _parse_pg_url(url: str):
    """
    Parse postgresql://user:password@host:port/dbname without urlparse.
    urlparse in Python 3.14 crashes when password contains [ or ].
    Uses rfind('@') so @ inside the password is handled correctly.
    """
    # strip scheme
    rest = url.split("://", 1)[1]

    # split userinfo from hostinfo on the LAST '@'
    at_idx = rest.rfind("@")
    userinfo = rest[:at_idx]
    hostinfo = rest[at_idx + 1:]

    # split user : password (first colon only)
    colon_idx = userinfo.index(":")
    user = userinfo[:colon_idx]
    password = userinfo[colon_idx + 1:]

    # split host:port / dbname
    if "/" in hostinfo:
        hostport, dbname = hostinfo.split("/", 1)
    else:
        hostport, dbname = hostinfo, "postgres"

    if ":" in hostport:
        host, port_str = hostport.rsplit(":", 1)
        port = int(port_str)
    else:
        host, port = hostport, 5432

    return user, password, host, port, dbname


def _build_engine():
    raw_url = _get_raw_url()

    if raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql://", 1)

    if raw_url.startswith("sqlite"):
        return create_engine(raw_url, connect_args={"check_same_thread": False})

    user, password, host, port, dbname = _parse_pg_url(raw_url)

    sa_url = SA_URL.create(
        drivername="postgresql+pg8000",
        username=user,
        password=password,
        host=host,
        port=port,
        database=dbname,
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
