from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.security import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserResponse
from app.services.personal_library import ensure_personal_kb

router = APIRouter()

def _get_user_by_identifier(db: Session, identifier: str) -> User | None:
    """Find a user by username or email."""
    normalized_identifier = identifier.strip().lower()
    return (
        db.query(User)
        .filter(
            (User.username == identifier.strip())
            | (User.email == normalized_identifier)
        )
        .first()
    )

@router.post("/register", response_model=UserResponse)
def register(*, db: Session = Depends(get_db), user_in: UserCreate) -> Any:
    """
    Register a new user.
    """
    normalized_username = user_in.username.strip()
    normalized_email = user_in.email.lower()
    if not normalized_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пайдаланушы аты бос болмауы керек",
        )

    existing_user = (
        db.query(User)
        .filter(
            (User.username == normalized_username)
            | (User.email == normalized_email)
        )
        .first()
    )
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Бұл пайдаланушы аты немесе email бұрыннан бар",
        )

    user = User(
        email=normalized_email,
        username=normalized_username,
        hashed_password=security.get_password_hash(user_in.password),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    ensure_personal_kb(db, user)
    return user


@router.post("/token", response_model=Token)
def login_access_token(
    db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    user = _get_user_by_identifier(db, form_data.username)
    if not user or not security.verify_password(
        form_data.password, user.hashed_password or ""
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Қате пайдаланушы аты, email немесе құпиясөз",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пайдаланушы белсенді емес",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> Any:
    """Return the authenticated user."""
    return current_user


@router.post("/test-token", response_model=UserResponse)
def test_token(current_user: User = Depends(get_current_admin)) -> Any:
    """
    Test access token by getting current user.
    """
    return current_user
