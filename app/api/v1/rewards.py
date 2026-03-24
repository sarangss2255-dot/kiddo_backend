"""Reward endpoints."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import User, Reward, Redemption, RedemptionStatus, UserRole
from app.schemas import RewardCreate, RewardUpdate, RewardResponse, RedemptionCreate, RedemptionResponse
from app.api.deps import get_current_user, get_current_parent, get_current_admin

router = APIRouter(prefix="/rewards", tags=["Rewards"])


@router.get("/", response_model=List[RewardResponse])
async def list_rewards(
    db: Session = Depends(get_db)
):
    """List all available rewards."""
    rewards = db.query(Reward).filter(Reward.is_active == True).all()
    return [RewardResponse.model_validate(reward) for reward in rewards]


@router.post("/", response_model=RewardResponse, status_code=status.HTTP_201_CREATED)
async def create_reward(
    reward_data: RewardCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new reward (admin only)."""
    reward = Reward(**reward_data.model_dump())
    db.add(reward)
    db.commit()
    db.refresh(reward)
    return RewardResponse.model_validate(reward)


@router.put("/{reward_id}", response_model=RewardResponse)
async def update_reward(
    reward_id: str,
    reward_data: RewardUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update a reward (admin only)."""
    reward = db.query(Reward).filter(Reward.id == reward_id).first()
    if not reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reward not found"
        )

    update_data = reward_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(reward, key, value)

    db.commit()
    db.refresh(reward)
    return RewardResponse.model_validate(reward)


@router.delete("/{reward_id}")
async def delete_reward(
    reward_id: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Delete/deactivate a reward (admin only)."""
    reward = db.query(Reward).filter(Reward.id == reward_id).first()
    if not reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reward not found"
        )

    reward.is_active = False
    db.commit()
    return {"message": "Reward deactivated successfully"}


@router.post("/redeem", response_model=RedemptionResponse, status_code=status.HTTP_201_CREATED)
async def redeem_reward(
    redemption_data: RedemptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Redeem a reward."""
    if current_user.role != UserRole.KID:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only kids can redeem rewards"
        )

    reward = db.query(Reward).filter(
        Reward.id == redemption_data.reward_id,
        Reward.is_active == True
    ).first()
    if not reward:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reward not found"
        )

    if current_user.points_balance < reward.points_required:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not enough points"
        )

    # Deduct points
    current_user.points_balance -= reward.points_required

    # Create redemption
    redemption = Redemption(
        user_id=current_user.id,
        reward_id=reward.id,
        status=RedemptionStatus.PENDING
    )
    db.add(redemption)
    db.commit()
    db.refresh(redemption)

    return RedemptionResponse.model_validate(redemption)


@router.get("/redemptions", response_model=List[RedemptionResponse])
async def list_redemptions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List redemptions. Kids see their own, parents see their children's."""
    query = db.query(Redemption)

    if current_user.role == UserRole.KID:
        query = query.filter(Redemption.user_id == current_user.id)
    elif current_user.role == UserRole.PARENT:
        children_ids = [child.id for child in current_user.children]
        query = query.filter(Redemption.user_id.in_(children_ids))

    redemptions = query.order_by(Redemption.requested_at.desc()).all()
    return [RedemptionResponse.model_validate(r) for r in redemptions]


@router.post("/redemptions/{redemption_id}/approve", response_model=RedemptionResponse)
async def approve_redemption(
    redemption_id: str,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Approve a reward redemption (parent only)."""
    redemption = db.query(Redemption).filter(Redemption.id == redemption_id).first()
    if not redemption:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Redemption not found"
        )

    # Verify this is the parent of the kid
    kid = db.query(User).filter(User.id == redemption.user_id).first()
    if kid.parent_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only approve redemptions for your children"
        )

    redemption.status = RedemptionStatus.APPROVED
    db.commit()
    db.refresh(redemption)

    return RedemptionResponse.model_validate(redemption)


@router.post("/redemptions/{redemption_id}/complete", response_model=RedemptionResponse)
async def complete_redemption(
    redemption_id: str,
    current_user: User = Depends(get_current_parent),
    db: Session = Depends(get_db)
):
    """Mark a reward redemption as completed (parent only)."""
    redemption = db.query(Redemption).filter(Redemption.id == redemption_id).first()
    if not redemption:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Redemption not found"
        )

    redemption.status = RedemptionStatus.COMPLETED
    db.commit()
    db.refresh(redemption)

    return RedemptionResponse.model_validate(redemption)