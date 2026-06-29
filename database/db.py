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
    # customer_infos 마이그레이션
    with _engine.begin() as conn:
        ci_existing = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(customer_infos)").fetchall()
        }
        for col, typ in [("meeting_id", "INTEGER"), ("detected_at", "DATE")]:
            if col not in ci_existing:
                conn.exec_driver_sql(f"ALTER TABLE customer_infos ADD COLUMN {col} {typ}")
    with _engine.begin() as conn:
        existing = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(meeting_analyses)").fetchall()
        }
        for column_name, column_type in required_columns.items():
            if column_name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE meeting_analyses ADD COLUMN {column_name} {column_type}")
    # schedules 마이그레이션
    with _engine.begin() as conn:
        sch_existing = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(schedules)").fetchall()
        }
        new_sch_cols = {
            "briefing_sent": "BOOLEAN DEFAULT 0",
            "category_id": "INTEGER",
            "remind_times": "JSON",
            "recur_type": "TEXT",
            "recur_interval": "INTEGER DEFAULT 1",
            "recur_days_of_week": "JSON",
            "recur_end_date": "DATE",
            "recur_last_reminded": "DATE",
            "recur_last_briefing": "DATE",
        }
        for col, typedef in new_sch_cols.items():
            if col not in sch_existing:
                conn.exec_driver_sql(f"ALTER TABLE schedules ADD COLUMN {col} {typedef}")
    # schedule_categories 기본 시드
    with _engine.begin() as conn:
        count = conn.exec_driver_sql("SELECT COUNT(*) FROM schedule_categories").fetchone()[0]
        if count == 0:
            defaults = [
                ("미팅", "#3B82F6", 0),
                ("외근", "#10B981", 1),
                ("내부", "#8B5CF6", 2),
                ("개인", "#F59E0B", 3),
            ]
            for name, color, order in defaults:
                conn.exec_driver_sql(
                    "INSERT INTO schedule_categories (name, color, sort_order, created_at) VALUES (?, ?, ?, datetime('now'))",
                    (name, color, order),
                )
