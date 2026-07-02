from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.account import Account
from app.models.folder import Folder

router = APIRouter(prefix="/folders", tags=["folders"])


class FolderResponse(BaseModel):
    id: str
    account_id: str
    name: str
    folder_type: str
    remote_id: str | None = None


class FolderListResponse(BaseModel):
    folders: list[FolderResponse]


@router.get("", response_model=FolderListResponse)
async def list_folders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all mailbox folders across the current user's accounts."""
    result = await db.execute(
        select(Folder)
        .where(
            Folder.account_id.in_(
                select(Account.id).where(Account.user_id == user.id)
            )
        )
        .order_by(Folder.sort_order, Folder.name)
    )
    folders = result.scalars().all()
    return FolderListResponse(
        folders=[
            FolderResponse(
                id=str(f.id),
                account_id=str(f.account_id),
                name=f.name,
                folder_type=f.folder_type,
                remote_id=f.remote_id,
            )
            for f in folders
        ]
    )
