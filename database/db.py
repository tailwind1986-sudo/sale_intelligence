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
    _ensure_meeting_analysis_columns()


def _ensure_meeting_analysis_columns() -> None:
    required_columns = {
        "meeting_overview": "JSON",
        "topic_discussions": "JSON",
        "decisions": "JSON",
        "action_items_structured": "JSON",
        "risks_and_checks": "JSON",
        "relationship_notes": "JSON",
        "schedule_candidates": "JSON",
        "full_report": "TEXT",
        "analyzed_at": "DATETIME",
        "meeting_mood": "JSON",
    }
    with _engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(meeting_analyses)").fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE meeting_analyses ADD COLUMN {column_name} {column_type}")
