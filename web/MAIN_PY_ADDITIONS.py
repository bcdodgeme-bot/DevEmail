# ============================================
# main.py ADDITIONS — Add these to serve the React frontend
# ============================================
#
# These additions go into your existing app/main.py file.
# DO NOT replace your existing code — just add these lines.
#
# ---

# 1. Add these imports at the top of main.py:
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# 2. AFTER all your API router includes (app.include_router(...)),
#    add the static file serving:

# Path to the Vite build output
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

# Only mount if the static directory exists (i.e., frontend has been built)
if os.path.exists(STATIC_DIR):
    # Serve static assets (JS, CSS, images, fonts)
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(STATIC_DIR, "assets")),
        name="static-assets",
    )

    # Serve other static files at root level (favicon, logo, etc.)
    @app.get("/logo.png")
    async def serve_logo():
        filepath = os.path.join(STATIC_DIR, "logo.png")
        if os.path.exists(filepath):
            return FileResponse(filepath)

    @app.get("/favicon.png")
    async def serve_favicon():
        filepath = os.path.join(STATIC_DIR, "favicon.png")
        if os.path.exists(filepath):
            return FileResponse(filepath)

    # SPA catch-all — MUST be the very last route
    # This ensures React Router handles all non-API paths
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API routes
        if full_path.startswith("api"):
            return  # Let FastAPI handle it normally
        index_path = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)


# ============================================
# CORS UPDATE — Add the frontend URL if needed
# ============================================
#
# If you're running the frontend dev server separately,
# make sure http://localhost:3000 is in your CORS origins.
# This should already be configured based on your existing setup.
#
# For production, since the frontend is served from the same
# origin as the API, CORS isn't needed for the frontend.
# ============================================
