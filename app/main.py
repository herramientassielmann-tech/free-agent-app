from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import engine, SessionLocal
from app.models import Base, User
from app.auth import hash_password
from app.config import ADMIN_EMAIL, ADMIN_PASSWORD
from app.routers import auth, scripts, profile, admin


def _create_admin_if_missing(db: Session):
    existing = db.query(User).filter(User.email == ADMIN_EMAIL.lower()).first()
    if not existing:
        admin_user = User(
            email=ADMIN_EMAIL.lower(),
            password_hash=hash_password(ADMIN_PASSWORD),
            name="Administrador",
            is_admin=True,
            is_active=True,
            monthly_limit=None,
        )
        db.add(admin_user)
        db.commit()
        print(f"[INFO] Cuenta de administrador creada: {ADMIN_EMAIL}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _create_admin_if_missing(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Free Agent Academy — Generador de Guiones",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth.router)
app.include_router(scripts.router)
app.include_router(profile.router)
app.include_router(admin.router)


@app.exception_handler(303)
async def redirect_handler(request: Request, exc):
    return RedirectResponse(url=exc.headers.get("Location", "/login"), status_code=303)
