"""
SQLAlchemy ORM models for audia's SQLite database.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Paper(Base):
    """Academic paper (from ArXiv or uploaded manually)."""

    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    authors: Mapped[str] = mapped_column(Text, default="")       # JSON list
    abstract: Mapped[str] = mapped_column(Text, default="")
    arxiv_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    audio_files: Mapped[list[AudioFile]] = relationship(
        "AudioFile", back_populates="paper", cascade="all, delete-orphan"
    )

    @property
    def authors_list(self) -> list[str]:
        try:
            return json.loads(self.authors)
        except Exception:
            return [self.authors]

    def __repr__(self) -> str:
        return f"<Paper id={self.id} title={self.title!r}>"


class AudioFile(Base):
    """Generated audio file, linked to an optional Paper."""

    __tablename__ = "audio_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    tts_backend: Mapped[str] = mapped_column(String(32), default="edge-tts")
    tts_voice: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    paper: Mapped[Paper | None] = relationship("Paper", back_populates="audio_files")

    def __repr__(self) -> str:
        return f"<AudioFile id={self.id} filename={self.filename!r}>"


class ResearchSession(Base):
    """
    A research session: a user query → list of selected paper IDs.
    Useful for auditing and re-running searches.
    """

    __tablename__ = "research_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    paper_ids: Mapped[str] = mapped_column(Text, default="[]")  # JSON list of ints
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )

    @property
    def paper_ids_list(self) -> list[int]:
        try:
            return json.loads(self.paper_ids)
        except Exception:
            return []

    def __repr__(self) -> str:
        return f"<ResearchSession id={self.id} query={self.query!r}>"


class UserSetting(Base):
    """Persistent key-value store for user-configured pipeline settings."""

    __tablename__ = "user_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<UserSetting {self.key}={self.value!r}>"
