"""FastAPI server for storing Shopify store Consultation Entries."""

import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
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


@app.post("/api/consultations")
async def create_consultation(
    request: Request,
    db: Session = Depends(get_db),
) -> JSONResponse:
    form = await request.form()

    name = str(form.get("name") or "").strip()
    email = str(form.get("email") or "").strip()
    phone = str(form.get("phone") or "").strip()
    message = str(form.get("message") or "").strip()

    missing_fields = []
    if not name:
        missing_fields.append("name")
    if not email:
        missing_fields.append("email")
    if not phone:
        missing_fields.append("phone")
    if not message:
        missing_fields.append("message")

    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields: {', '.join(missing_fields)}",
        )

    entry = ConsultationEntry(
        name=name,
        email=email,
        phone=phone,
        message=message,
    )

    upload_items = []

    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile) and value.filename:
            upload_items.append(value)

    for upload in upload_items:
        suffix = Path(upload.filename).suffix.lower()
        stored_file_name = f"{uuid.uuid4().hex}{suffix}"
        dest = UPLOAD_DIR / stored_file_name

        content = await upload.read()
        dest.write_bytes(content)

        entry.files.append(
            ConsultationFile(
                file_name=upload.filename,
                stored_file_name=stored_file_name,
            )
        )

    db.add(entry)
    db.commit()
    db.refresh(entry)

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "id": entry.id,
            "file_count": len(entry.files),
            "message": "Consultation entry saved.",
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
