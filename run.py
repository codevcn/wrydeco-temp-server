"""Entry point: run the FastAPI server with uvicorn.

Dùng cho DEV (có reload). Trên VPS production nên chạy qua systemd/uvicorn
trực tiếp — xem deploy/wrydeco-server.service.
"""
import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENV", "dev") == "dev",
    )
