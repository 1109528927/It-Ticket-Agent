"""支撑大盘。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.request import get_db
from crud.dashboard import get_dashboard_stats
from model.user import User
from schema.ticket import DashboardStatsOut
from utils.auth import get_current_user
from utils.response import success_response

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def api_dashboard_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "support":
        raise HTTPException(status_code=403, detail="仅客服可查看大盘")
    data = await get_dashboard_stats(db)
    return success_response(
        message="ok",
        data=DashboardStatsOut.model_validate(data).model_dump(),
    )
