"""Admin endpoints."""
from typing import List
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.models import User, Task, GameSession, Reward, Redemption, TaskStatus, UserRole
from app.schemas import UserResponse, TaskResponse, RewardCreate, RewardResponse
from app.api.deps import get_current_admin
from app.models.models import User as UserModel

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dashboard")
async def get_dashboard_stats(
    current_user: UserModel = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get admin dashboard statistics."""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # User stats
    total_users = db.query(func.count(User.id)).scalar()
    total_kids = db.query(func.count(User.id)).filter(User.role == UserRole.KID).scalar()
    total_parents = db.query(func.count(User.id)).filter(User.role == UserRole.PARENT).scalar()
    active_users = db.query(func.count(User.id)).filter(User.is_active == True).scalar()
    new_users_this_week = db.query(func.count(User.id)).filter(User.created_at >= week_ago).scalar()

    # Task stats
    total_tasks = db.query(func.count(Task.id)).scalar()
    completed_tasks = db.query(func.count(Task.id)).filter(Task.status == TaskStatus.APPROVED).scalar()
    pending_tasks = db.query(func.count(Task.id)).filter(Task.status == TaskStatus.PENDING).scalar()
    tasks_this_week = db.query(func.count(Task.id)).filter(Task.created_at >= week_ago).scalar()
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

    # Game stats
    total_games_played = db.query(func.count(GameSession.id)).scalar()
    games_this_week = db.query(func.count(GameSession.id)).filter(GameSession.completed_at >= week_ago).scalar()
    total_points_awarded = db.query(func.sum(GameSession.points_earned)).scalar() or 0

    # Reward stats
    total_redemptions = db.query(func.count(Redemption.id)).scalar()
    pending_redemptions = db.query(func.count(Redemption.id)).filter(Redemption.status == "pending").scalar()

    return {
        "users": {
            "total": total_users,
            "kids": total_kids,
            "parents": total_parents,
            "active": active_users,
            "new_this_week": new_users_this_week
        },
        "tasks": {
            "total": total_tasks,
            "completed": completed_tasks,
            "pending": pending_tasks,
            "this_week": tasks_this_week,
            "completion_rate": round(completion_rate, 1)
        },
        "games": {
            "total_played": total_games_played,
            "this_week": games_this_week,
            "total_points_awarded": total_points_awarded
        },
        "rewards": {
            "total_redemptions": total_redemptions,
            "pending": pending_redemptions
        }
    }


@router.get("/analytics/tasks")
async def get_task_analytics(
    days: int = 30,
    current_user: UserModel = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get task completion analytics."""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)

    # Daily task completions
    daily_stats = db.query(
        func.date(Task.approved_at).label("date"),
        func.count(Task.id).label("completed")
    ).filter(
        Task.status == TaskStatus.APPROVED,
        Task.approved_at >= start_date
    ).group_by(func.date(Task.approved_at)).all()

    # Tasks by category
    category_stats = db.query(
        Task.category_id,
        func.count(Task.id).label("count")
    ).filter(Task.created_at >= start_date).group_by(Task.category_id).all()

    # Tasks by status
    status_stats = db.query(
        Task.status,
        func.count(Task.id).label("count")
    ).group_by(Task.status).all()

    return {
        "period_days": days,
        "daily_completions": [
            {"date": str(stat.date), "completed": stat.completed}
            for stat in daily_stats
        ],
        "by_category": [
            {"category_id": str(stat.category_id), "count": stat.count}
            for stat in category_stats
        ],
        "by_status": [
            {"status": stat.status.value, "count": stat.count}
            for stat in status_stats
        ]
    }


@router.get("/analytics/users")
async def get_user_analytics(
    days: int = 30,
    current_user: UserModel = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Get user activity analytics."""
    now = datetime.utcnow()
    start_date = now - timedelta(days=days)

    # User registrations over time
    registrations = db.query(
        func.date(User.created_at).label("date"),
        func.count(User.id).label("count")
    ).filter(User.created_at >= start_date).group_by(func.date(User.created_at)).all()

    # Most active users
    active_users = db.query(
        User.id,
        User.name,
        func.count(Task.id).label("tasks_completed")
    ).join(Task, Task.assigned_to == User.id).filter(
        Task.status == TaskStatus.APPROVED,
        Task.approved_at >= start_date
    ).group_by(User.id).order_by(func.count(Task.id).desc()).limit(10).all()

    # Top point earners
    top_earners = db.query(
        User.id,
        User.name,
        User.points_balance
    ).filter(User.role == UserRole.KID).order_by(User.points_balance.desc()).limit(10).all()

    return {
        "period_days": days,
        "registrations": [
            {"date": str(reg.date), "count": reg.count}
            for reg in registrations
        ],
        "most_active": [
            {"user_id": str(u.id), "name": u.name, "tasks_completed": u.tasks_completed}
            for u in active_users
        ],
        "top_earners": [
            {"user_id": str(u.id), "name": u.name, "points": u.points_balance}
            for u in top_earners
        ]
    }


@router.get("/users", response_model=List[UserResponse])
async def list_all_users(
    role: str = None,
    is_active: bool = None,
    current_user: UserModel = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """List all users with optional filters."""
    query = db.query(User)

    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    users = query.order_by(User.created_at.desc()).all()
    return [UserResponse.model_validate(u) for u in users]


@router.post("/rewards", response_model=RewardResponse, status_code=status.HTTP_201_CREATED)
async def create_reward(
    reward_data: RewardCreate,
    current_user: UserModel = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new reward."""
    from app.models.models import Reward

    reward = Reward(**reward_data.model_dump())
    db.add(reward)
    db.commit()
    db.refresh(reward)
    return RewardResponse.model_validate(reward)


@router.get("/tasks", response_model=List[TaskResponse])
async def list_all_tasks(
    status: str = None,
    limit: int = 100,
    current_user: UserModel = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """List all tasks."""
    from app.models.models import TaskStatus as TS

    query = db.query(Task)

    if status:
        query = query.filter(Task.status == TS(status))

    tasks = query.order_by(Task.created_at.desc()).limit(limit).all()
    return [TaskResponse.model_validate(t) for t in tasks]


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: UserModel = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Deactivate a user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.commit()
    return {"message": "User deactivated"}