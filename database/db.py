from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base

_DB_PATH = Path(__file__).parent.parent / "data" / "sales_intelligence.db"
_DB_PATH.parent.mkdir(exist_ok=True)

_engine = create_engine(f"sqlite:///{_DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


def create_database() -> None:
    Base.metadata.create_all(_engine)
