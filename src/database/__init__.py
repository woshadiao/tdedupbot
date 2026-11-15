"""Persistent fingerprint baseline for review-group submissions."""
import os
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    Index,
    String,
    and_,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.config import DEDUP_DB_URL


class Base(DeclarativeBase):
    pass


class SubmissionContent(Base):
    __tablename__ = "submission_contents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Grouping key for the submission (the main bot's first content message id).
    submission_key: Mapped[str] = mapped_column(String(190), nullable=False)
    # Telegram media album id; NULL for single messages. Items of one album
    # share this id (within one chat) and are not duplicates of each other.
    media_group_id: Mapped[str] = mapped_column(String(190), nullable=True)
    # photo | video | gif | document | sticker | text
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    phash: Mapped[str] = mapped_column(String(32), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    text_simhash: Mapped[str] = mapped_column(String(32), nullable=True)
    # Bot API file identity used to avoid repeated downloads.
    file_unique_id: Mapped[str] = mapped_column(String(190), nullable=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    submitter_id: Mapped[str] = mapped_column(String(190), nullable=True)
    first_seen_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (
        Index("idx_pcid", "file_unique_id"),
        Index("idx_phash", "phash"),
        Index("idx_content", "content_hash"),
        Index("idx_text", "text_hash"),
        Index("idx_simhash", "text_simhash"),
        # Each source message contributes at most one row of each type.
        Index(
            "idx_source", "source_chat_id", "source_message_id", "type", unique=True
        ),
    )

    def __repr__(self):
        return (
            f"SubmissionContent(key={self.submission_key}, type={self.type}, "
            f"msg={self.source_message_id}, first_seen={self.first_seen_date})"
        )


class DB:
    def __init__(self, database_url):
        if database_url.startswith("sqlite"):
            # File path is everything after "sqlite:///" -- a relative
            # (``sqlite:///data/dedup.db``) or absolute (``sqlite:////abs.db``)
            # path. Create its directory so the first connect can create the
            # file. In-memory (``sqlite:``) has no file to create.
            path = database_url.removeprefix("sqlite:///")
            if path:
                os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        self._ensure_columns()

    def _ensure_columns(self):
        """Add columns introduced after the original schema.

        ``create_all`` only creates missing tables; an existing database keeps
        its old column set, so ``media_group_id`` is added in place. Rows
        written before the upgrade keep NULL there: their media group cannot
        be told apart from a single message reliably.
        """
        columns = {
            column["name"]
            for column in inspect(self.engine).get_columns("submission_contents")
        }
        if "media_group_id" not in columns:
            with self.engine.begin() as conn:
                conn.execute(text(
                    "ALTER TABLE submission_contents "
                    "ADD COLUMN media_group_id VARCHAR(190)"
                ))

    def select(self, table, *conditions):
        with self.Session.begin() as session:
            stmt = select("*").select_from(table)
            if conditions:
                stmt = stmt.where(and_(*conditions))
            return session.execute(stmt).mappings().all()

db = DB(DEDUP_DB_URL)


def record_items(items):
    """Insert a list of ``SubmissionContent`` field-dicts.

    Return only inserted rows, with their database ids filled in. A duplicate
    message does not add an unpersisted row to the in-memory baseline.
    """
    inserted = []
    for it in items:
        try:
            with db.Session.begin() as session:
                obj = SubmissionContent(**it)
                session.add(obj)
                session.flush()
                session.refresh(obj)
                it["id"] = obj.id
            inserted.append(it)
        except IntegrityError:  # already recorded
            pass
    return inserted


def find_exact(column, value):
    """Rows matching a single exact hash column (``content_hash`` / ``text_hash``)."""
    return db.select(SubmissionContent, getattr(SubmissionContent, column) == value)


def load_photo_phashes():
    """All photo rows carrying a pHash (the baseline for the NumPy scan)."""
    return db.select(
        SubmissionContent,
        SubmissionContent.type == "photo",
        SubmissionContent.phash.isnot(None),
    )


def load_text_simhashes():
    """All text rows carrying a SimHash (the baseline for the SimHash scan)."""
    return db.select(
        SubmissionContent,
        SubmissionContent.type == "text",
        SubmissionContent.text_simhash.isnot(None),
    )


def load_file_unique_ids():
    """All rows that carry a ``file_unique_id`` (Bot-side cache)."""
    return db.select(SubmissionContent, SubmissionContent.file_unique_id.isnot(None))
