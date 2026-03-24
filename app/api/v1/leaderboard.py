"""Leaderboard endpoints."""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.models import User, GameSession, Task, LeaderboardEntry, LeaderboardScope, LeaderboardPeriod, TaskStatus
from app.schemas import LeaderboardEntryResponse, UserResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


def calculate_rankings(db: Session, period: LeaderboardPeriod, scope: LeaderboardScope, user_id: str = None):
    """Calculate leaderboard rankings."""
    now = datetime.utcnow()

    # Determine period range
    if period == LeaderboardPeriod.DAILY:
        period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(days=1)
    elif period == LeaderboardPeriod.WEEKLY:
        period_start = now - timedelta(days=now.weekday())
        period_start = period_start.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end = period_start + timedelta(weeks=1)
    elif period == LeaderboardPeriod.MONTHLY:
        period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            period_end = period_start.replace(year=now.year + 1, month=1)
        else:
            period_end = period_start.replace(month=now.month + 1)
    else:  # ALL_TIME
        period_start = None
        period_end = None

    # Build query for users with points
    query = db.query(
        User.id,
        User.name,
        User.avatar_url,
        User.points_balance,
        func.count(Task.id).filter(Task.status == TaskStatus.APPROVED).label("tasks_completed"),
        func.count(GameSession.id).label("games_played")
    ).outerjoin(Task, Task.assigned_to == User.id).outerjoin(GameSession, GameSession.user_id == User.id)

    # Filter by period if not all time
    if period_start:
        query = query.filter(
            (Task.approved_at >= period_start) | (Task.approved_at.is_(None)),
            (GameSession.completed_at >= period_start) | (GameSession.completed_at.is_(None))
        )

    # Filter by scope (family vs global)
    if scope == LeaderboardScope.FAMILY and user_id:
        # Get the family (parent's children)
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            if user.parent_id:
                # User is a kid, get siblings
                family_ids = [u.id for u in db.query(User).filter(User.parent_id == user.parent_id).all()]
            else:
                # User is a parent, get children
                family_ids = [u.id for u in user.children]
            query = query.filter(User.id.in_(family_ids))

    query = query.filter(User.role == "kid").group_by(User.id).order_by(User.points_balance.desc())

    return query.all()


@router.get("/global", response_model=List[LeaderboardEntryResponse])
async def get_global_leaderboard(
    period: str = Query("weekly", regex="^(daily|weekly|monthly|all_time)$"),
    limit: int = Query(20, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get global leaderboard."""
    period_enum = LeaderboardPeriod(period)

    results = calculate_rankings(db, period_enum, LeaderboardScope.GLOBAL)

    entries = []
    for rank, row in enumerate(results[:limit], 1):
        entry = LeaderboardEntryResponse(
            id=row.id,
            user_id=row.id,
            period=period,
            scope="global",
            total_points=row.points_balance or 0,
            tasks_completed=row.tasks_completed or 0,
            games_played=row.games_played or 0,
            rank=rank,
            user=UserResponse(
                id=row.id,
                name=row.name,
                email="",
                role="kid",
                avatar_url=row.avatar_url,
                points_balance=row.points_balance or 0,
                is_active=True,
                created_at=datetime.utcnow()
            )
        )
        entries.append(entry)

    return entries


@router.get("/family", response_model=List[LeaderboardEntryResponse])
async def get_family_leaderboard(
    period: str = Query("weekly", regex="^(daily|weekly|monthly|all_time)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get family leaderboard."""
    period_enum = LeaderboardPeriod(period)

    results = calculate_rankings(db, period_enum, LeaderboardScope.FAMILY, str(current_user.id))

    entries = []
    for rank, row in enumerate(results, 1):
        entry = LeaderboardEntryResponse(
            id=row.id,
            user_id=row.id,
            period=period,
            scope="family",
            total_points=row.points_balance or 0,
            tasks_completed=row.tasks_completed or 0,
            games_played=row.games_played or 0,
            rank=rank,
            user=UserResponse(
                id=row.id,
                name=row.name,
                email="",
                role="kid",
                avatar_url=row.avatar_url,
                points_balance=row.points_balance or 0,
                is_active=True,
                created_at=datetime.utcnow()
            )
        )
        entries.append(entry)

    return entries


@router.get("/my-rank")
async def get_my_rank(
    period: str = Query("weekly", regex="^(daily|weekly|monthly|all_time)$"),
    scope: str = Query("global", regex="^(global|family)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get current user's rank."""
    period_enum = LeaderboardPeriod(period)
    scope_enum = LeaderboardScope(scope)

    results = calculate_rankings(db, period_enum, scope_enum, str(current_user.id))

    for rank, row in enumerate(results, 1):
        if str(row.id) == str(current_user.id):
            return {
                "rank": rank,
                "total_points": row.points_balance or 0,
                "tasks_completed": row.tasks_completed or 0,
                "games_played": row.games_played or 0
            }

    return {
        "rank": None,
        "total_points": current_user.points_balance,
        "tasks_completed": 0,
        "games_played": 0
    }