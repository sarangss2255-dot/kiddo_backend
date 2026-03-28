"""Firebase Admin helpers for verifying ID tokens."""
from __future__ import annotations

from pathlib import Path

import firebase_admin
from firebase_admin import auth, credentials

from app.config import settings


def initialize_firebase_admin():
    """Initialize the Firebase Admin SDK once for the process."""
    try:
        return firebase_admin.get_app()
    except ValueError:
        credential = _get_credential()
        options = {}
        if settings.firebase_project_id:
            options["projectId"] = settings.firebase_project_id
        return firebase_admin.initialize_app(credential, options or None)


def is_firebase_admin_initialized() -> bool:
    """Return whether Firebase Admin has been initialized."""
    try:
        firebase_admin.get_app()
        return True
    except ValueError:
        return False


def _get_credential():
    if settings.firebase_credentials_path:
        credentials_path = Path(settings.firebase_credentials_path)
        return credentials.Certificate(str(credentials_path))

    return credentials.ApplicationDefault()


def verify_firebase_id_token(id_token: str) -> dict:
    """Verify a Firebase ID token and return its decoded claims."""
    app = initialize_firebase_admin()
    return auth.verify_id_token(
        id_token,
        app=app,
        check_revoked=False,
        clock_skew_seconds=60,
    )
