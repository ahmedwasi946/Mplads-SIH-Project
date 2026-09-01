from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.schemas.insights import (
    InsightCategory,
    InsightPriority,
    ProjectInsightsResponse,
    SmartInsightListResponse,
    SmartInsightResponse,
    SmartInsightSummaryResponse,
)
from app.services.insight_service import (
    build_insight_summary,
    get_project_insights,
    list_insights,
)


router = APIRouter(
    tags=["smart-insights"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/insights", response_model=SmartInsightListResponse)
def get_insights(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    project_id: int | None = Query(default=None, ge=1),
    category: InsightCategory | None = Query(default=None),
    priority: InsightPriority | None = Query(default=None),
    db: Session = Depends(get_db),
):
    items, total = list_insights(
        db,
        page=page,
        page_size=page_size,
        project_id=project_id,
        category=category,
        priority=priority,
    )
    return SmartInsightListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size if total else 0,
    )


@router.get("/insights/summary", response_model=SmartInsightSummaryResponse)
def get_insight_summary(db: Session = Depends(get_db)):
    return build_insight_summary(db)


@router.get(
    "/projects/{project_id}/insights",
    response_model=ProjectInsightsResponse,
)
def get_project_insight_list(
    project_id: int,
    db: Session = Depends(get_db),
):
    if project_id < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Project ID must be a positive integer.",
        )
    response = get_project_insights(db, project_id=project_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return response