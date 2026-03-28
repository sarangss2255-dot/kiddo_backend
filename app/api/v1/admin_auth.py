"""Admin authentication endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.firebase_auth import verify_firebase_id_token
from app.core.security import create_admin_access_token
from app.database import get_db
from app.models.models import AdminAccount
from app.schemas import (
    AdminAccountResponse,
    AdminGoogleLoginRequest,
    AdminTokenResponse,
)

router = APIRouter(prefix="/admin/auth", tags=["Admin Authentication"])


def _is_allowed_admin_email(email: str) -> bool:
    email = email.lower()
    if email in settings.admin_allowed_email_list:
        return True

    domain = email.split("@")[-1].lower()
    return domain in settings.admin_allowed_domain_list


@router.post("/google", response_model=AdminTokenResponse)
async def google_admin_login(
    request: AdminGoogleLoginRequest,
    db: Session = Depends(get_db),
):
    """Authenticate an admin using a Firebase Google ID token."""
    try:
        claims = verify_firebase_id_token(request.id_token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Firebase ID token",
        ) from exc

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase account did not provide an email",
        )

    if not claims.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin email must be verified",
        )

    admin = db.query(AdminAccount).filter(AdminAccount.email == email).first()
    if admin is None:
        if not _is_allowed_admin_email(email):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This Google account is not allowed to access admin",
            )

        admin = AdminAccount(
            email=email,
            name=(claims.get("name") or email.split("@")[0]).strip(),
            avatar_url=claims.get("picture"),
            is_active=True,
        )
        db.add(admin)
    elif not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin account is inactive",
        )

    admin.name = (claims.get("name") or admin.name).strip()
    admin.avatar_url = claims.get("picture") or admin.avatar_url
    admin.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(admin)

    access_token = create_admin_access_token(
        {"sub": admin.email, "admin_id": str(admin.id)}
    )

    return AdminTokenResponse(
        access_token=access_token,
        admin=AdminAccountResponse.model_validate(admin),
    )
