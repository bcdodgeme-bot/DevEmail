from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check(
    db: AsyncSession = Depends(get_db),
):
    """Check API and database health."""
    checks = {"api": "ok", "database": "error"}

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = str(e)

    status_ok = all(v == "ok" for v in checks.values())
    return {"status": "healthy" if status_ok else "degraded", "checks": checks}
