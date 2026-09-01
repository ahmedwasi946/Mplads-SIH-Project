from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.db.database import Base, engine
from fastapi.middleware.cors import CORSMiddleware

from app.api.alerts import router as alerts_router
from app.api.analytics import router as analytics_router
from app.api.anomalies import router as anomalies_router
from app.api.auth import router as auth_router
from app.api.datasets import router as datasets_router
from app.api.insights import router as insights_router
from app.api.preprocessing import router as preprocessing_router
from app.api.projects import router as projects_router
from app.api.reports import router as reports_router
from app.api.risk import router as risk_router
from app.api.routes import router
from app.api.users import router as users_router
from app.core.config import settings
from app.models import (
    AnomalyDetectionResult,
    Dataset,
    DatasetProcessingResult,
    Project,
    RiskAssessment,
    User,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(
    title="MPLADS Sentinel AI API",
    description="Foundation API for the MPLADS Sentinel AI government analytics platform.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(alerts_router)
app.include_router(projects_router)
app.include_router(datasets_router)
app.include_router(analytics_router)
app.include_router(preprocessing_router)
app.include_router(anomalies_router)
app.include_router(risk_router)
app.include_router(insights_router)
app.include_router(reports_router)