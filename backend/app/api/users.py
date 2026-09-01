from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.db.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import ManagedUserCreate, UserResponse, UserRoleUpdate
from app.services.auth_service import create_managed_user, update_user_role


router = APIRouter(
    prefix="/users",
    tags=["user-management"],
    dependencies=[Depends(require_roles(UserRole.ADMIN))],
)


@router.get("", response_model=list[UserResponse])
def list_users(
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    statement = select(User).order_by(User.created_at, User.id)
    if not include_inactive:
        statement = statement.where(User.is_active.is_(True))
    return db.scalars(statement).all()


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: ManagedUserCreate, db: Session = Depends(get_db)):
    try:
        return create_managed_user(db, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.patch("/{user_id}/role", response_model=UserResponse)
def change_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_roles(UserRole.ADMIN)),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    if user.id == current_admin.id and payload.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An administrator cannot remove their own Admin role.",
        )
    return update_user_role(db, user, payload.role)