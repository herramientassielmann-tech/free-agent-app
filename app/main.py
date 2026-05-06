import logging
import traceback
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info("Cuenta de administrador creada: %s", ADMIN_EMAIL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
async def redirect_handler(_request: Request, exc: HTTPException):
    location = (exc.headers or {}).get("Location", "/login")
    return RedirectResponse(url=location, status_code=303)


@app.exception_handler(Exception)
async def generic_error_handler(_request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": str(exc)})
