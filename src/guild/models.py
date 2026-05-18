"""SQLAlchemy 2.0 ORM models for the Guild thread model.

These classes map to the tables created in migrations/versions/0001_initial_schema.py.
All schema changes go through Alembic — do not use Base.metadata.create_all().
"""
from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    anchor_type: Mapped[str] = mapped_column(String)
    anchor_id: Mapped[str] = mapped_column(String)
    anchor_url: Mapped[str] = mapped_column(String)
    anchor_title: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="unnoticed")
    owner_type: Mapped[Optional[str]] = mapped_column(String)
    owner_id: Mapped[Optional[str]] = mapped_column(String)
    parent_thread_id: Mapped[Optional[str]] = mapped_column(ForeignKey("threads.id"))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    events: Mapped[list[ThreadEvent]] = relationship(back_populates="thread")
    artifacts: Mapped[list[ThreadArtifact]] = relationship(back_populates="thread")
    notes: Mapped[list[ThreadNote]] = relationship(back_populates="thread")

    __table_args__ = (
        CheckConstraint(
            "state IN ('unnoticed','noticed','claimed','executing',"
            "'pr_open','blocked','planned','done','abandoned')",
            name="threads_state_check",
        ),
        CheckConstraint(
            "owner_type IN ('worker','human')",
            name="threads_owner_type_check",
        ),
        UniqueConstraint("anchor_type", "anchor_id", name="threads_anchor"),
    )


class ThreadEvent(Base):
    __tablename__ = "thread_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"))
    source: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)
    actor_id: Mapped[Optional[str]] = mapped_column(String)
    actor_name: Mapped[Optional[str]] = mapped_column(String)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    thread: Mapped[Thread] = relationship(back_populates="events")


class ThreadArtifact(Base):
    __tablename__ = "thread_artifacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"))
    type: Mapped[str] = mapped_column(String)
    external_id: Mapped[str] = mapped_column(String)
    url: Mapped[Optional[str]] = mapped_column(String)
    title: Mapped[Optional[str]] = mapped_column(String)
    state: Mapped[Optional[str]] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    thread: Mapped[Thread] = relationship(back_populates="artifacts")


class ThreadNote(Base):
    __tablename__ = "thread_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id"))
    author_id: Mapped[str] = mapped_column(String)
    note_type: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    thread: Mapped[Thread] = relationship(back_populates="notes")

    __table_args__ = (
        CheckConstraint(
            "note_type IN ('decision','status','error','observation')",
            name="thread_notes_type_check",
        ),
    )
