from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from .config import DB_PATH, ensure_dirs

ensure_dirs()

engine = create_engine(
    f"sqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 5},
    pool_size=3,
    max_overflow=2,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, _):
    cur = dbapi_connection.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA temp_store=MEMORY")
    cur.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register SQLModel tables)

    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
              row_id UNINDEXED,
              entity_id UNINDEXED,
              type UNINDEXED,
              page UNINDEXED,
              title,
              body,
              tokenize='trigram'
            )
            """
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_annotation_paper ON annotation(paper_id)"
        )
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS idx_metric_run_key ON metric(run_id, key, step)"
        )


def exec_sql(session: Session, sql: str, params: dict | None = None):
    from sqlalchemy import text

    return session.execute(text(sql), params or {})


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
