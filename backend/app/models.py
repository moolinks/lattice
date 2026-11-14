from __future__ import annotations

from typing import Optional

from sqlalchemy import Column, Text
from sqlmodel import Field, SQLModel


class Counter(SQLModel, table=True):
    __tablename__ = "counter"
    prefix: str = Field(primary_key=True)
    value: int = 0


class Paper(SQLModel, table=True):
    __tablename__ = "paper"

    id: str = Field(primary_key=True)
    title: str
    authors: Optional[str] = Field(default=None, sa_column=Column(Text))
    year: Optional[int] = None
    venue: Optional[str] = None
    abstract: Optional[str] = Field(default=None, sa_column=Column(Text))
    doi: Optional[str] = Field(default=None, unique=True, index=True)
    arxiv_id: Optional[str] = Field(default=None, unique=True, index=True)
    url: Optional[str] = None
    pdf_path: Optional[str] = None
    bibkey: Optional[str] = Field(default=None, unique=True, index=True)
    bibtex: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: str = "unread"
    rating: Optional[int] = None
    ai_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    note_path: Optional[str] = None
    created_at: str
    updated_at: str


class Annotation(SQLModel, table=True):
    __tablename__ = "annotation"

    id: Optional[int] = Field(default=None, primary_key=True)
    paper_id: str = Field(foreign_key="paper.id", index=True)
    page: Optional[int] = None
    rects: Optional[str] = Field(default=None, sa_column=Column(Text))
    quote: Optional[str] = Field(default=None, sa_column=Column(Text))
    comment: Optional[str] = Field(default=None, sa_column=Column(Text))
    color: str = "amber"
    created_at: str


class Idea(SQLModel, table=True):
    __tablename__ = "idea"

    id: str = Field(primary_key=True)
    title: str
    status: str = "seed"
    priority: int = 0
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    path: Optional[str] = None
    created_at: str
    updated_at: str


class Experiment(SQLModel, table=True):
    __tablename__ = "experiment"

    id: str = Field(primary_key=True)
    idea_id: Optional[str] = Field(default=None, foreign_key="idea.id", index=True)
    title: str
    hypothesis: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: str = "planned"
    verdict: Optional[str] = None
    path: Optional[str] = None
    created_at: str
    updated_at: str


class Run(SQLModel, table=True):
    __tablename__ = "run"

    id: str = Field(primary_key=True)
    experiment_id: str = Field(foreign_key="experiment.id", index=True)
    status: str = "running"
    params: Optional[str] = Field(default=None, sa_column=Column(Text))
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    command: Optional[str] = Field(default=None, sa_column=Column(Text))
    git_commit: Optional[str] = None
    git_dirty: Optional[int] = None
    seed: Optional[int] = None
    host: Optional[str] = None
    log_path: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class Metric(SQLModel, table=True):
    __tablename__ = "metric"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    key: str = Field(index=True)
    step: int = 0
    value: float = 0.0
    ts: str


class Artifact(SQLModel, table=True):
    __tablename__ = "artifact"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(foreign_key="run.id", index=True)
    kind: str = "figure"
    path: str
    created_at: str


class Draft(SQLModel, table=True):
    __tablename__ = "draft"

    id: str = Field(primary_key=True)
    title: str
    venue: Optional[str] = None
    status: str = "writing"
    path: Optional[str] = None
    created_at: str
    updated_at: str


class Link(SQLModel, table=True):
    __tablename__ = "link"

    src_id: str = Field(primary_key=True)
    dst_id: str = Field(primary_key=True)
    relation: str = Field(primary_key=True)
    created_at: str


class Tag(SQLModel, table=True):
    __tablename__ = "tag"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="tag.id")


class EntityTag(SQLModel, table=True):
    __tablename__ = "entity_tag"

    entity_id: str = Field(primary_key=True)
    tag_id: int = Field(primary_key=True, foreign_key="tag.id")


class Inbox(SQLModel, table=True):
    __tablename__ = "inbox"

    id: Optional[int] = Field(default=None, primary_key=True)
    content: str = Field(sa_column=Column(Text))
    processed: int = 0
    created_at: str


class FeedItem(SQLModel, table=True):
    __tablename__ = "feed_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    arxiv_id: str = Field(unique=True, index=True)
    title: str
    authors: Optional[str] = Field(default=None, sa_column=Column(Text))
    abstract: Optional[str] = Field(default=None, sa_column=Column(Text))
    published: Optional[str] = None
    score: float = 0.0
    status: str = "new"
    fetched_at: str


class Chunk(SQLModel, table=True):
    __tablename__ = "chunk"

    id: str = Field(primary_key=True)
    paper_id: str = Field(foreign_key="paper.id", index=True)
    page: Optional[int] = None
    text: str = Field(sa_column=Column(Text))


class Setting(SQLModel, table=True):
    __tablename__ = "setting"

    key: str = Field(primary_key=True)
    value: str


class ImportJob(SQLModel, table=True):
    __tablename__ = "import_job"

    id: str = Field(primary_key=True)
    source: str
    kind: str
    status: str = "queued"
    progress: int = 0
    message: str = "等待开始"
    paper_id: Optional[str] = None
    created_at: str
    updated_at: str


class SummaryRecord(SQLModel, table=True):
    __tablename__ = "summary_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    paper_id: str = Field(foreign_key="paper.id", index=True)
    mode: str
    model: Optional[str] = None
    summary: str = Field(sa_column=Column(Text))
    evidence: str = Field(default="[]", sa_column=Column(Text))
    prompt_version: str
    created_at: str
