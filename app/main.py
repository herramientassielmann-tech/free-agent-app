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


def _migrate_db(db: Session):
    """Agrega columnas nuevas a tablas existentes sin romper datos previos."""
    from sqlalchemy import text, inspect as sa_inspect
    simple = [
        "ALTER TABLE scripts ADD COLUMN thumbnail_path VARCHAR(500)",
        "ALTER TABLE scripts ADD COLUMN estructura_detectada TEXT",
        "ALTER TABLE scripts ADD COLUMN promesa TEXT",
        "ALTER TABLE realtor_profiles ADD COLUMN cliente_ideal TEXT",
        "ALTER TABLE realtor_profiles ADD COLUMN objeciones TEXT",
        "ALTER TABLE realtor_profiles ADD COLUMN casos_exito TEXT",
        "ALTER TABLE realtor_profiles ADD COLUMN objetivo_cta TEXT",
        "ALTER TABLE realtor_profiles ADD COLUMN temas_evitar TEXT",
        "ALTER TABLE realtor_profiles ADD COLUMN telefono VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN temp_password VARCHAR(255)",
    ]
    for sql in simple:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback()

    # Migración de perfiles: quitar UNIQUE(user_id) y añadir profile_name + is_active
    cols = {c["name"] for c in sa_inspect(engine).get_columns("realtor_profiles")}
    if "profile_name" not in cols:
        db.execute(text("""
            CREATE TABLE realtor_profiles_new (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                profile_name VARCHAR(100) NOT NULL DEFAULT 'Mi Perfil',
                is_active  BOOLEAN NOT NULL DEFAULT 1,
                display_name VARCHAR(100),
                market     VARCHAR(100),
                tone       VARCHAR(20) NOT NULL DEFAULT 'cercano',
                speaking_notes TEXT,
                specialization VARCHAR(30) NOT NULL DEFAULT 'todo_tipo',
                about_me   TEXT
            )
        """))
        db.execute(text("""
            INSERT INTO realtor_profiles_new
                (id, user_id, profile_name, is_active, display_name, market,
                 tone, speaking_notes, specialization, about_me)
            SELECT id, user_id, 'Mi Perfil', 1, display_name, market,
                   tone, speaking_notes, specialization, about_me
            FROM realtor_profiles
        """))
        db.execute(text("DROP TABLE realtor_profiles"))
        db.execute(text("ALTER TABLE realtor_profiles_new RENAME TO realtor_profiles"))
        db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _migrate_db(db)          # primero columnas nuevas
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
