"""Database engine, session factory and ORM models."""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConsultationEntry(Base):
    """A consultation request submitted by a customer.

    Theo contract mới (doc/consultation-form.md): khách chỉ cung cấp một
    phương thức liên hệ duy nhất qua ``phone_or_email``; backend tự phân loại
    thành email/phone và lưu cả giá trị raw lẫn normalized.
    """

    __tablename__ = "consultation_entries"

    id = Column(Integer, primary_key=True, index=True)

    # Public lead identifier trả về cho client (vd: "con_ab12...").
    public_id = Column(String(64), nullable=False, unique=True, index=True)

    name = Column(String(255), nullable=False)

    # Contact — một field duy nhất từ frontend, backend phân loại.
    contact_value_raw = Column(String(320), nullable=False)
    contact_type = Column(String(16), nullable=False)  # "email" | "phone"
    contact_value_normalized = Column(String(320), nullable=False, index=True)

    message = Column(Text, nullable=False)  # "Short request"

    # Optional preferred consultation time (chưa phải booking đã xác nhận).
    consultation_time_raw = Column(String(64), nullable=True)
    preferred_date = Column(Date, nullable=True)
    preferred_time = Column(Time, nullable=True)
    timezone = Column(String(64), nullable=True)  # frontend chưa cung cấp

    lead_status = Column(String(32), nullable=False, default="new")
    schedule_status = Column(String(32), nullable=False, default="not_requested")
    source = Column(
        String(64), nullable=False, default="shopify_customization_page"
    )

    created_at = Column(DateTime, default=_utcnow, nullable=False)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)
    contacted_at = Column(DateTime, nullable=True)

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

    # Original (sanitized, chỉ để hiển thị) và stored (on-disk) filename.
    file_name = Column(String(512), nullable=False)
    stored_file_name = Column(String(512), nullable=False)

    mime_type = Column(String(128), nullable=True)  # MIME đã xác minh
    size_bytes = Column(Integer, nullable=True)
    checksum = Column(String(128), nullable=True)  # SHA-256

    entry = relationship("ConsultationEntry", back_populates="files")


class CustomSizeRequest(Base):
    """A quick custom size request submitted by a customer."""

    __tablename__ = "custom_size_requests"

    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(String(255), nullable=False)
    product_handle = Column(String(512), nullable=False)
    product_name = Column(String(512), nullable=False)
    custom_size_description = Column(Text, nullable=False)
    customer_contact = Column(String(320), nullable=False)

    created_at = Column(DateTime, default=_utcnow, nullable=False)


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
