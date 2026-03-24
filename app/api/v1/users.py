"""User endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, UserRole
from app.schemas import UserResponse, UserUpdate, UserWithChildren, ChildCreate
from app.api.deps import get_current_user, get_current_parent, get_current_admin
from app.core.security import hash_password

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse.model_validate(current_user)


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update current user profile."""
    update_data = user_data.model_dump(exclude_unset=True)

    # Check email uniqueness if changing email
    if "email" in update_data and update_data["email"] != current_user.email:
        existing = db.query(User).filter(User.email == update_data["email"]).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )

    for key, value in update_data.items():
        setattr(current_user, key, value)

    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.get("/me/children", response_model=List[UserResponse])
async def get_my_children(
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Get children of current parent."""
    children = db.query(User).filter(User.parent_id == current_user.id).all()
    return [UserResponse.model_validate(child) for child in children]


@router.post("/me/children", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_child(
    child_data: ChildCreate,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Create a child account linked to current parent."""
    # Check if email already exists
    existing = db.query(User).filter(User.email == child_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    hashed_password = hash_password(child_data.password)
    child = User(
        name=child_data.name,
        email=child_data.email,
        password_hash=hashed_password,
        role=UserRole.KID,
        parent_id=current_user.id,
        date_of_birth=child_data.date_of_birth
    )
    db.add(child)
    db.commit()
    db.refresh(child)

    return UserResponse.model_validate(child)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get user by ID (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return UserResponse.model_validate(user)


@router.get("/", response_model=List[UserResponse])
async def list_users(
    role: str = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """List all users (admin only)."""
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    users = query.all()
    return [UserResponse.model_validate(user) for user in users]


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Delete/deactivate a user (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    user.is_active = False
    db.commit()
    return {"message": "User deactivated successfully"}