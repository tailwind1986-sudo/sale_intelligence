from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base


_db_path = Path(__file__).parent.parent / "data" / "sales_intelligence.db"
_db_path.parent.mkdir(exist_ok=True)

_engine = create_engine(
    f"sqlite:///{_db_path}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    bind=_engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def create_database() -> None:
    Base.metadata.create_all(_engine)
