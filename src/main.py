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


@app.on_event("startup")
def on_startup() -> None:
    init_db()


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
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    message: str = Form(...),
    # Field chuẩn: files
    files: list[UploadFile] | None = File(default=None),
    # Field dự phòng: file
    # Dùng để tránh lỗi nếu frontend cũ đang gửi name="file"
    legacy_files: list[UploadFile] | None = File(default=None, alias="file"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    entry = ConsultationEntry(
        name=name,
        email=email,
        phone=phone,
        message=message,
    )

    upload_items: list[UploadFile] = []
    if files:
        upload_items.extend(files)
    if legacy_files:
        upload_items.extend(legacy_files)

    for upload in upload_items:
        if not upload.filename:
            continue

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
