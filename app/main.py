import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.routers import auth, contacts, health, accounts, messages, calendars

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(contacts.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(messages.router, prefix="/api")
app.include_router(calendars.router, prefix="/api")


@app.get("/")
async def root():
    return {
        "app": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/api/docs",
    }


# --------------------------------------------------
# Static file serving for React frontend
# --------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

if os.path.exists(STATIC_DIR):
    # Serve Vite-built assets (JS, CSS, etc.)
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

    # SPA catch-all — serves index.html for all non-API routes
    # This MUST be after all other routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Check if the file exists in static dir (e.g., logo.png, favicon.png)
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Otherwise serve index.html for React Router
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
