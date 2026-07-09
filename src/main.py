"""FastAPI server for storing Shopify store Consultation Entries."""
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .config import TEMPLATES_DIR, UPLOAD_DIR
from .database import ConsultationEntry, get_db, init_db

app = FastAPI(title="Wrydeco Shopify Consultation Server")

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
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Receive a FormData submission from the browser and store it."""
    stored_file_name: str | None = None
    original_file_name: str | None = None

    # Persist the optional uploaded image/file to disk with a unique name.
    if file is not None and file.filename:
        original_file_name = file.filename
        suffix = Path(file.filename).suffix
        stored_file_name = f"{uuid.uuid4().hex}{suffix}"
        dest = UPLOAD_DIR / stored_file_name
        content = await file.read()
        dest.write_bytes(content)

    entry = ConsultationEntry(
        name=name,
        email=email,
        phone=phone,
        message=message,
        file_name=original_file_name,
        stored_file_name=stored_file_name,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    return JSONResponse(
        status_code=201,
        content={
            "success": True,
            "id": entry.id,
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
