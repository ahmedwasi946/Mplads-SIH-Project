from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.project import ProjectStatus


class ProjectFields(BaseModel):
    project_name: str = Field(min_length=1, max_length=255)
    constituency: str = Field(min_length=1, max_length=150)
    state: str = Field(min_length=1, max_length=100)
    district: str = Field(min_length=1, max_length=100)
    sanctioned_amount: Decimal = Field(ge=0, max_digits=15, decimal_places=2)
    utilized_amount: Decimal = Field(ge=0, max_digits=15, decimal_places=2)
    project_status: ProjectStatus
    start_date: date | None = None
    expected_completion_date: date | None = None

    @field_validator(
        "project_name",
        "constituency",
        "state",
        "district",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must not be blank.")
        return cleaned


class ProjectCreate(ProjectFields):
    pass


class ProjectUpdate(BaseModel):
    project_name: str | None = Field(default=None, min_length=1, max_length=255)
    constituency: str | None = Field(default=None, min_length=1, max_length=150)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    district: str | None = Field(default=None, min_length=1, max_length=100)
    sanctioned_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=15, decimal_places=2
    )
    utilized_amount: Decimal | None = Field(
        default=None, ge=0, max_digits=15, decimal_places=2
    )
    project_status: ProjectStatus | None = None
    start_date: date | None = None
    expected_completion_date: date | None = None

    @field_validator(
        "project_name",
        "constituency",
        "state",
        "district",
        mode="before",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value must not be blank.")
        return cleaned


class ProjectResponse(ProjectFields):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime