from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Cookie, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def _authenticated_user(access_token: Optional[str], db: Session):
    """Devuelve (usuario del claim 'sub', payload). Lanza 303 a /login si no hay sesión válida."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        headers={"Location": "/login"},
    )
    if not access_token:
        raise credentials_exception
    payload = decode_token(access_token)
    if not payload:
        raise credentials_exception
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    user = db.query(User).filter(User.id == int(user_id), User.is_active == True).first()
    if not user:
        raise credentials_exception
    return user, payload


def get_current_user(
    access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    real_user, payload = _authenticated_user(access_token, db)

    # Impersonación: un admin puede "entrar como" un realtor (claim "imp").
    # El usuario efectivo pasa a ser el realtor, pero recordamos al admin real.
    imp_id = payload.get("imp")
    if imp_id is not None and real_user.is_admin:
        target = db.query(User).filter(
            User.id == int(imp_id), User.is_admin == False
        ).first()
        if target:
            target.impersonated = True
            target.impersonator_id = real_user.id
            target.impersonator_name = real_user.name
            return target

    real_user.impersonated = False
    return real_user


def get_real_user(
    access_token: Optional[str] = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """El usuario realmente autenticado (el admin cuando impersona), ignorando el claim 'imp'."""
    user, _ = _authenticated_user(access_token, db)
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Acceso restringido a administradores.")
    return current_user
