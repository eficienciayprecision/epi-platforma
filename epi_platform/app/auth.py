"""Autenticacion JWT — SOLO para personal interno (admin / engineer).
El cliente final ya NO necesita usuario ni contrasena: usa el formulario
de contacto opcional (ver ContactInfo) para iniciar y recibir su oferta."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import UserModel

SECRET_KEY = os.getenv("EPI_JWT_SECRET", "epi-dev-secret-change-in-production-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("EPI_TOKEN_EXPIRE_MIN", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# auto_error=False -> las rutas publicas pueden funcionar sin token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


class UserRole(str, Enum):
    ADMIN = "admin"
    ENGINEER = "engineer"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: UserRole
    username: str


class User(BaseModel):
    username: str
    full_name: str
    role: UserRole
    disabled: bool = False
    company: str = "Eficiencia y Precision Industrial S.L."


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: str
    role: UserRole = UserRole.ENGINEER


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def authenticate_user(db: Session, username: str, password: str) -> Optional[UserModel]:
    user = db.query(UserModel).filter(UserModel.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        return None
    if user.disabled:
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_staff_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Requiere token valido de personal interno. Usar SOLO en rutas de staff
    (calculo manual, informe interno, catalogo, scraping...)."""
    if not token:
        raise HTTPException(status_code=401, detail="Se requiere acceso de personal interno",
                             headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Token invalido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token invalido o expirado")

    row = db.query(UserModel).filter(UserModel.username == username).first()
    if not row or row.disabled:
        raise HTTPException(status_code=401, detail="Usuario no encontrado o deshabilitado")
    return User(
        username=row.username,
        full_name=row.full_name,
        role=UserRole(row.role),
        disabled=row.disabled,
        company=row.company or "",
    )


def require_roles(*roles: UserRole):
    async def _check(user: User = Depends(get_current_staff_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Rol '{user.role.value}' no autorizado. Requiere: {[r.value for r in roles]}",
            )
        return user
    return _check


require_admin = require_roles(UserRole.ADMIN)
require_staff = require_roles(UserRole.ADMIN, UserRole.ENGINEER)
