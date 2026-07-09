"""Database engine, session factory and ORM models."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

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

    # Original filename and the stored (on-disk) filename, if a file was sent.
    file_name = Column(String(512), nullable=True)
    stored_file_name = Column(String(512), nullable=True)

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )


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
