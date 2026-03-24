"""Pydantic schemas for request/response validation."""
import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field
from app.models.models import UserRole, TaskStatus, TaskPriority, RedemptionStatus, PvpMatchStatus


# ============= User Schemas =============
class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    role: UserRole = UserRole.KID
    date_of_birth: Optional[datetime] = None


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=100)
    parent_id: Optional[uuid.UUID] = None


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None
    date_of_birth: Optional[datetime] = None


class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    avatar_url: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    date_of_birth: Optional[datetime] = None
    points_balance: int = 0
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class UserWithChildren(UserResponse):
    children: List["UserResponse"] = []


# ============= Auth Schemas =============
class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ============= Task Category Schemas =============
class TaskCategoryBase(BaseModel):
    name: str = Field(..., max_length=50)
    icon: Optional[str] = None
    color_code: Optional[str] = None
    description: Optional[str] = None


class TaskCategoryCreate(TaskCategoryBase):
    pass


class TaskCategoryResponse(TaskCategoryBase):
    id: uuid.UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ============= Task Template Schemas =============
class TaskTemplateBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    suggested_points: int = 10
    age_min: int = 0
    age_max: int = 18


class TaskTemplateCreate(TaskTemplateBase):
    pass


class TaskTemplateUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    suggested_points: Optional[int] = None
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    is_active: Optional[bool] = None


class TaskTemplateResponse(TaskTemplateBase):
    id: uuid.UUID
    is_active: bool = True
    created_at: datetime
    category: Optional[TaskCategoryResponse] = None

    class Config:
        from_attributes = True


# ============= Task Schemas =============
class TaskBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    points: int = 10
    due_date: Optional[datetime] = None


class TaskCreate(TaskBase):
    assigned_to: uuid.UUID


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    priority: Optional[TaskPriority] = None
    points: Optional[int] = None
    due_date: Optional[datetime] = None
    status: Optional[TaskStatus] = None


class TaskResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    assigned_to: uuid.UUID
    created_by: uuid.UUID
    status: TaskStatus
    priority: TaskPriority
    points: int
    due_date: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    approved_by: Optional[uuid.UUID] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    category: Optional[TaskCategoryResponse] = None
    assigned_user: Optional[UserResponse] = None
    creator: Optional[UserResponse] = None

    class Config:
        from_attributes = True


class TaskApprovalRequest(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


# ============= Reward Schemas =============
class RewardBase(BaseModel):
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    points_required: int = Field(..., ge=1)
    icon: Optional[str] = None
    image_url: Optional[str] = None


class RewardCreate(RewardBase):
    pass


class RewardUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    points_required: Optional[int] = Field(None, ge=1)
    icon: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None


class RewardResponse(RewardBase):
    id: uuid.UUID
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


# ============= Redemption Schemas =============
class RedemptionCreate(BaseModel):
    reward_id: uuid.UUID


class RedemptionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    reward_id: uuid.UUID
    status: RedemptionStatus
    requested_at: datetime
    processed_at: Optional[datetime] = None
    processed_by: Optional[uuid.UUID] = None
    reward: Optional[RewardResponse] = None
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True


# ============= Game Schemas =============
class GameSessionCreate(BaseModel):
    game_type_id: uuid.UUID
    score: int = 0
    difficulty: str = "medium"
    duration_seconds: int = 0


class GameSessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    game_type_id: uuid.UUID
    score: int
    points_earned: int
    difficulty: str
    duration_seconds: int
    completed_at: datetime

    class Config:
        from_attributes = True


class GameTypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    points_reward_base: int
    icon: Optional[str] = None
    is_active: bool = True

    class Config:
        from_attributes = True


# ============= Leaderboard Schemas =============
class LeaderboardEntryResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    period: str
    scope: str
    total_points: int
    tasks_completed: int
    games_played: int
    rank: Optional[int] = None
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True


# ============= PVP Chess Schemas =============
class PvpInviteResponse(BaseModel):
    match_id: uuid.UUID
    invite_code: str
    time_control_seconds: int


class PvpJoinResponse(BaseModel):
    match_id: uuid.UUID
    invite_code: str
    status: PvpMatchStatus


class PvpResultResponse(BaseModel):
    match_id: uuid.UUID
    winner_id: Optional[uuid.UUID] = None
    result: str
    points_awarded: int = 0


# ============= Child Registration =============
class ChildCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    date_of_birth: Optional[datetime] = None


# Update forward references
UserWithChildren.model_rebuild()
