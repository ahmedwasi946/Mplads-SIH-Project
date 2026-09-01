from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.schemas.analytics import DashboardAnalyticsResponse
from app.services.analytics_service import get_dashboard_analytics


router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/dashboard", response_model=DashboardAnalyticsResponse)
def dashboard_analytics(db: Session = Depends(get_db)):
    return get_dashboard_analytics(db)