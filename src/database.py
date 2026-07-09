"""Database engine, session factory and ORM models."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + threads
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ConsultationEntry(Base):
    """A consultation request submitted by a customer."""

    __tablename__ = "consultation_entries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)  # "Yêu cầu ngắn gọn"

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # One entry can have many uploaded files.
    files = relationship(
        "ConsultationFile",
        back_populates="entry",
        cascade="all, delete-orphan",
    )


class ConsultationFile(Base):
    """A single file/image attached to a consultation entry."""

    __tablename__ = "consultation_files"

    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(
        Integer, ForeignKey("consultation_entries.id"), nullable=False, index=True
    )

    # Original filename and the stored (on-disk) filename.
    file_name = Column(String(512), nullable=False)
    stored_file_name = Column(String(512), nullable=False)

    entry = relationship("ConsultationEntry", back_populates="files")


def init_db() -> None:
    """Create tables if they do not exist yet."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
