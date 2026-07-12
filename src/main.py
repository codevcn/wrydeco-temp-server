"""FastAPI server for storing Shopify store Consultation Entries."""

import hashlib
import mimetypes
import re
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile as StarletteUploadFile
from .config import TEMPLATES_DIR, UPLOAD_DIR
from .database import ConsultationEntry, ConsultationFile, get_db, init_db

app = FastAPI(title="Wrydeco Shopify Consultation Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Vẫn giữ static route để có thể truy cập trực tiếp file nếu cần.
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB mỗi ảnh

IMAGE_UPLOAD_DIR = UPLOAD_DIR / "images"

# --- Consultation form contract (doc/consultation-form.md) ---------------

# Attachment: chỉ chấp nhận MIME đã xác minh bằng magic bytes.
CONSULTATION_ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024  # 10MB mỗi file
MAX_ATTACHMENTS_PER_REQUEST = 10
MAX_TOTAL_ATTACHMENT_BYTES = 30 * 1024 * 1024  # 30MB mỗi request

NAME_MIN_LEN, NAME_MAX_LEN = 2, 255
CONTACT_MAX_LEN = 320
MESSAGE_MIN_LEN, MESSAGE_MAX_LEN = 10, 10_000

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_ALLOWED_RE = re.compile(r"^\+?[\d\s().\-]+$")
_SCHEDULE_RE = re.compile(
    r"^(\d{2}):(\d{2})\s+(AM|PM),\s+(\d{2})/(\d{2})/(\d{4})$"
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    IMAGE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/api/health")
def healthcheck() -> JSONResponse:
    return JSONResponse(
        {
            "message": "Shopify Server responses Hello!!!",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _safe_upload_path_from_relative(relative_path: str) -> Path:
    """
    Lấy file trong thư mục uploads theo relative path.
    Chặn path traversal kiểu ../../etc/passwd.
    """
    upload_root = UPLOAD_DIR.resolve()
    file_path = (UPLOAD_DIR / relative_path).resolve()

    try:
        file_path.relative_to(upload_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return file_path


def _safe_uploaded_path(stored_file_name: str) -> Path:
    """
    Trả về đường dẫn file upload an toàn.
    Chặn path traversal kiểu ../../etc/passwd.
    """
    upload_root = UPLOAD_DIR.resolve()
    file_path = (UPLOAD_DIR / stored_file_name).resolve()

    try:
        file_path.relative_to(upload_root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path.")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found.")

    return file_path


def _content_disposition(disposition: str, filename: str) -> str:
    """
    Tạo Content-Disposition an toàn, hỗ trợ tên file tiếng Việt.
    """
    safe_ascii = filename.encode("ascii", "ignore").decode().replace('"', "")
    if not safe_ascii:
        safe_ascii = "file"

    encoded = quote(filename)
    return f"{disposition}; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"


class _FieldError(Exception):
    """Một lỗi validation gắn với một field, để gom vào response 422."""

    def __init__(self, field: str, code: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.code = code
        self.message = message


def _classify_contact(raw: str):
    """
    Phân loại ``phone_or_email`` thành email hoặc phone và normalize.
    Trả về (contact_type, normalized) hoặc (None, None) nếu không hợp lệ.
    """
    if _EMAIL_RE.match(raw):
        local, _, domain = raw.rpartition("@")
        return "email", f"{local}@{domain.lower()}"

    # Không phải email → thử parse như số điện thoại.
    if _PHONE_ALLOWED_RE.match(raw):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 7:
            prefix = "+" if raw.lstrip().startswith("+") else ""
            return "phone", f"{prefix}{digits}"

    return None, None


def _parse_consultation_time(raw: str):
    """
    Parse ``hh:mm AM|PM, dd/mm/yyyy`` → (date, time).
    Raise _FieldError nếu format/giá trị không hợp lệ hoặc ngày đã qua.
    """
    match = _SCHEDULE_RE.match(raw)
    if not match:
        raise _FieldError(
            "consultation_time",
            "INVALID_SCHEDULE",
            "Use the format hh:mm AM|PM, dd/mm/yyyy.",
        )

    hh, mm, period, dd, mo, yyyy = match.groups()
    hour, minute = int(hh), int(mm)

    if not 1 <= hour <= 12:
        raise _FieldError(
            "consultation_time", "INVALID_SCHEDULE", "Hour must be 01-12."
        )
    if minute % 5 != 0:
        raise _FieldError(
            "consultation_time",
            "INVALID_SCHEDULE",
            "Minutes must be in 5-minute steps.",
        )

    # 12h → 24h.
    if period == "AM":
        hour24 = 0 if hour == 12 else hour
    else:
        hour24 = 12 if hour == 12 else hour + 12

    try:
        preferred_date = date(int(yyyy), int(mo), int(dd))
    except ValueError:
        raise _FieldError(
            "consultation_time", "INVALID_SCHEDULE", "That date does not exist."
        )

    if preferred_date < datetime.now(timezone.utc).date():
        raise _FieldError(
            "consultation_time",
            "PAST_SCHEDULE",
            "The preferred date is in the past.",
        )

    return preferred_date, time(hour24, minute)


def _sniff_attachment_mime(content: bytes) -> Optional[str]:
    """Xác minh MIME bằng magic bytes; None nếu không thuộc loại cho phép."""
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:5] == b"%PDF-":
        return "application/pdf"
    return None


def _sanitize_original_name(filename: str) -> str:
    """Chỉ giữ basename để lưu hiển thị; không dùng làm path lưu trữ."""
    return Path(filename).name or "file"


def _field(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def _error_response(status_code: int, code: str, message: str, errors=None):
    body = {"success": False, "code": code, "message": message}
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(status_code=status_code, content=body)


@app.post("/api/consultations")
async def create_consultation(
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    try:
        form = await request.form()
    except Exception:
        return _error_response(
            400, "MALFORMED_REQUEST", "The multipart request is malformed."
        )

    # --- 1. Business fields: name, phone_or_email, message ---------------
    errors = []

    name = str(form.get("name") or "").strip()
    if not name:
        errors.append(_field("name", "REQUIRED", "Name is required."))
    elif not NAME_MIN_LEN <= len(name) <= NAME_MAX_LEN:
        errors.append(
            _field(
                "name",
                "INVALID_LENGTH",
                f"Name must be {NAME_MIN_LEN}-{NAME_MAX_LEN} characters.",
            )
        )

    # phone_or_email là contract mới; fallback email/phone cho giai đoạn migrate.
    contact_raw = str(form.get("phone_or_email") or "").strip()
    if not contact_raw:
        contact_raw = (
            str(form.get("email") or "").strip()
            or str(form.get("phone") or "").strip()
        )

    contact_type = None
    contact_normalized = None
    if not contact_raw:
        errors.append(
            _field(
                "phone_or_email",
                "REQUIRED",
                "A phone number or email address is required.",
            )
        )
    elif len(contact_raw) > CONTACT_MAX_LEN:
        errors.append(
            _field(
                "phone_or_email",
                "INVALID_LENGTH",
                f"Contact must be at most {CONTACT_MAX_LEN} characters.",
            )
        )
    else:
        contact_type, contact_normalized = _classify_contact(contact_raw)
        if contact_type is None:
            errors.append(
                _field(
                    "phone_or_email",
                    "INVALID_CONTACT",
                    "Enter a valid phone number or email address.",
                )
            )

    message = str(form.get("message") or "").strip()
    if not message:
        errors.append(_field("message", "REQUIRED", "A short request is required."))
    elif not MESSAGE_MIN_LEN <= len(message) <= MESSAGE_MAX_LEN:
        errors.append(
            _field(
                "message",
                "INVALID_LENGTH",
                f"Message must be {MESSAGE_MIN_LEN}-{MESSAGE_MAX_LEN} characters.",
            )
        )

    # --- 2. Optional scheduler -------------------------------------------
    consultation_time_raw = str(form.get("consultation_time") or "").strip()
    preferred_date = None
    preferred_time = None
    schedule_status = "not_requested"
    if consultation_time_raw:
        try:
            preferred_date, preferred_time = _parse_consultation_time(
                consultation_time_raw
            )
            schedule_status = "requested"
        except _FieldError as exc:
            errors.append(_field(exc.field, exc.code, exc.message))

    if errors:
        return _error_response(
            422,
            "VALIDATION_ERROR",
            "The consultation request contains invalid fields.",
            errors,
        )

    # --- 3. Optional attachments (validate all trước khi ghi đĩa) --------
    raw_uploads = [
        value
        for _, value in form.multi_items()
        if isinstance(value, StarletteUploadFile) and value.filename
    ]

    if len(raw_uploads) > MAX_ATTACHMENTS_PER_REQUEST:
        return _error_response(
            413,
            "TOO_MANY_FILES",
            f"At most {MAX_ATTACHMENTS_PER_REQUEST} files are allowed.",
        )

    validated = []
    total_bytes = 0
    for upload in raw_uploads:
        content = await upload.read()
        size = len(content)

        if size > MAX_ATTACHMENT_BYTES:
            return _error_response(
                413, "FILE_TOO_LARGE", "Each file must be at most 10MB."
            )

        total_bytes += size
        if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
            return _error_response(
                413, "REQUEST_TOO_LARGE", "Total upload size exceeds 30MB."
            )

        sniffed = _sniff_attachment_mime(content)
        if sniffed is None:
            return _error_response(
                415,
                "UNSUPPORTED_FILE_TYPE",
                "Only JPEG, PNG and PDF files are allowed.",
            )

        validated.append((upload, content, sniffed, size))

    # --- 4. Persist lead + attachments atomically ------------------------
    entry = ConsultationEntry(
        public_id=f"con_{uuid.uuid4().hex}",
        name=name,
        contact_value_raw=contact_raw,
        contact_type=contact_type,
        contact_value_normalized=contact_normalized,
        message=message,
        consultation_time_raw=consultation_time_raw or None,
        preferred_date=preferred_date,
        preferred_time=preferred_time,
        lead_status="new",
        schedule_status=schedule_status,
        source="shopify_customization_page",
    )

    written_paths = []
    try:
        for upload, content, sniffed, size in validated:
            extension = CONSULTATION_ALLOWED_TYPES[sniffed]
            stored_file_name = f"{uuid.uuid4().hex}{extension}"
            dest = UPLOAD_DIR / stored_file_name
            dest.write_bytes(content)
            written_paths.append(dest)

            entry.files.append(
                ConsultationFile(
                    file_name=_sanitize_original_name(upload.filename),
                    stored_file_name=stored_file_name,
                    mime_type=sniffed,
                    size_bytes=size,
                    checksum=hashlib.sha256(content).hexdigest(),
                )
            )

        db.add(entry)
        db.commit()
        db.refresh(entry)
    except Exception:
        db.rollback()
        for path in written_paths:  # tránh orphan file
            path.unlink(missing_ok=True)
        return _error_response(
            500, "INTERNAL_ERROR", "Could not save the consultation request."
        )

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "id": entry.public_id,
            "lead_status": entry.lead_status,
            "schedule_status": entry.schedule_status,
            "message": "Consultation request received.",
        },
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    entries = (
        db.query(ConsultationEntry).order_by(ConsultationEntry.created_at.desc()).all()
    )

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "entries": entries,
        },
    )


@app.get("/admin/files/{file_id}/view")
def view_uploaded_file(file_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """
    Mở file trong tab mới.
    Ảnh/video/pdf sẽ được browser preview nếu hỗ trợ.
    """
    file_record = (
        db.query(ConsultationFile).filter(ConsultationFile.id == file_id).first()
    )

    if not file_record:
        raise HTTPException(status_code=404, detail="File record not found.")

    file_path = _safe_uploaded_path(file_record.stored_file_name)

    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={
            "Content-Disposition": _content_disposition(
                "inline",
                file_record.file_name or file_record.stored_file_name,
            )
        },
    )


@app.get("/admin/files/{file_id}/download")
def download_uploaded_file(file_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """
    Tải file về máy với tên gốc.
    """
    file_record = (
        db.query(ConsultationFile).filter(ConsultationFile.id == file_id).first()
    )

    if not file_record:
        raise HTTPException(status_code=404, detail="File record not found.")

    file_path = _safe_uploaded_path(file_record.stored_file_name)

    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={
            "Content-Disposition": _content_disposition(
                "attachment",
                file_record.file_name or file_record.stored_file_name,
            )
        },
    )


@app.post("/api/upload-image")
async def upload_image(
    request: Request,
    image: UploadFile = File(...),
) -> JSONResponse:
    """
    Upload 1 file ảnh, lưu vào server và trả về URL public để xem ảnh.
    Field name khi gửi FormData phải là: image
    """

    if not image.filename:
        raise HTTPException(status_code=400, detail="Image file is required.")

    content_type = image.content_type or ""

    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only jpg, png, webp, and gif images are allowed.",
        )

    content = await image.read()

    if len(content) > MAX_IMAGE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Image exceeds 10MB limit.",
        )

    IMAGE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    extension = ALLOWED_IMAGE_CONTENT_TYPES[content_type]
    stored_file_name = f"{uuid.uuid4().hex}{extension}"
    dest = IMAGE_UPLOAD_DIR / stored_file_name

    dest.write_bytes(content)

    # Build absolute public URL.
    # Dùng X-Forwarded-Proto để khi chạy sau Nginx HTTPS vẫn trả https://
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)

    image_url = f"{scheme}://{host}/uploads/images/{stored_file_name}"

    return JSONResponse(
        status_code=201,
        content={
            "image_url": image_url,
        },
    )


@app.get("/view-uploads", response_class=HTMLResponse)
def view_uploads_page(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    """
    Trang hiển thị toàn bộ file đang nằm trong thư mục uploads/.
    Bao gồm:
    - file từ consultation form
    - ảnh từ /api/upload-image
    - các file upload khác nếu có
    """

    db_files = db.query(ConsultationFile).all()

    original_name_by_stored_name = {f.stored_file_name: f.file_name for f in db_files}

    entry_id_by_stored_name = {f.stored_file_name: f.entry_id for f in db_files}

    uploaded_files = []

    if UPLOAD_DIR.exists():
        for file_path in UPLOAD_DIR.rglob("*"):
            if not file_path.is_file():
                continue

            relative_path = file_path.relative_to(UPLOAD_DIR).as_posix()
            stat = file_path.stat()

            media_type, _ = mimetypes.guess_type(str(file_path))
            if not media_type:
                media_type = "application/octet-stream"

            folder = file_path.parent.relative_to(UPLOAD_DIR).as_posix()
            if folder == ".":
                folder = "/"

            uploaded_files.append(
                {
                    "display_name": original_name_by_stored_name.get(
                        file_path.name,
                        file_path.name,
                    ),
                    "stored_name": file_path.name,
                    "relative_path": relative_path,
                    "folder": folder,
                    "size": _format_file_size(stat.st_size),
                    "size_bytes": stat.st_size,
                    "media_type": media_type,
                    "entry_id": entry_id_by_stored_name.get(file_path.name),
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime,
                        timezone.utc,
                    ).strftime("%Y-%m-%d %H:%M:%S UTC"),
                }
            )

    uploaded_files.sort(key=lambda item: item["modified_at"], reverse=True)

    return templates.TemplateResponse(
        "view_uploads.html",
        {
            "request": request,
            "uploaded_files": uploaded_files,
        },
    )


@app.get("/view-uploads/download")
def download_uploaded_file_by_path(
    path: str = Query(...),
    db: Session = Depends(get_db),
) -> FileResponse:
    """
    Download 1 file bất kỳ trong thư mục uploads/.
    Query:
    /view-uploads/download?path=images/abc.jpg
    """

    file_path = _safe_upload_path_from_relative(path)

    file_record = (
        db.query(ConsultationFile)
        .filter(ConsultationFile.stored_file_name == file_path.name)
        .first()
    )

    download_name = file_record.file_name if file_record else file_path.name

    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={
            "Content-Disposition": _content_disposition(
                "attachment",
                download_name,
            )
        },
    )
