"""FastAPI server for storing Shopify store Consultation Entries."""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import TEMPLATES_DIR, UPLOAD_DIR
from .database import ConsultationEntry, ConsultationFile, get_db, init_db

app = FastAPI(title="Wrydeco Shopify Consultation Server")

# Cho phép MỌI origin gửi request đến (public API).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # mọi domain
    allow_credentials=False,  # phải False khi allow_origins = "*"
    allow_methods=["*"],      # mọi HTTP method
    allow_headers=["*"],      # mọi header
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Serve uploaded files so the admin table can link/preview them.
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/health")
def healthcheck() -> JSONResponse:
    """Healthcheck endpoint."""
    return JSONResponse(
        {
            "message": "Shopify Server responses Hello!!!",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.post("/api/consultations")
async def create_consultation(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Receive a FormData submission from the browser and store it.

    The `files` field is optional and may contain multiple images/files.
    """
    entry = ConsultationEntry(
        name=name,
        email=email,
        phone=phone,
        message=message,
    )

    # Persist each uploaded file to disk with a unique name and link it.
    for upload in files:
        if not upload.filename:
            continue  # skip empty file parts
        suffix = Path(upload.filename).suffix
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
    """Render the Admin Manager Page listing all stored entries."""
    entries = (
        db.query(ConsultationEntry)
        .order_by(ConsultationEntry.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin.html", {"request": request, "entries": entries}
    )
