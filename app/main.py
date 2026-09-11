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
from app.routers import auth, scripts, profile, admin, chatbot, robert, ideas, editor, biblioteca, crm, bienvenida, webhooks


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
        "ALTER TABLE users ADD COLUMN es_alumno BOOLEAN DEFAULT 0",
        "ALTER TABLE tareas_equipo ADD COLUMN notas TEXT",
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

    # Tareas del equipo: `asignado_a` era una clave ajena a users.id y pasa a ser
    # el nombre de la persona. Robert, David y Kevin entran los tres con la misma
    # cuenta, así que el responsable es una etiqueta y no un usuario.
    # En SQLite cambiar el tipo de una columna obliga a rehacer la tabla.
    try:
        tipos = {c["name"]: str(c["type"]).upper()
                 for c in sa_inspect(engine).get_columns("tareas_equipo")}
    except Exception:
        tipos = {}
    if "INTEGER" in tipos.get("asignado_a", ""):
        db.execute(text("""
            CREATE TABLE tareas_equipo_new (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                texto         VARCHAR(300) NOT NULL,
                asignado_a    VARCHAR(20),
                fecha_limite  DATE,
                prioridad     VARCHAR(10) NOT NULL DEFAULT 'normal',
                estado        VARCHAR(12) NOT NULL DEFAULT 'pendiente',
                completada_en DATETIME,
                avisada_en    DATETIME,
                created_at    DATETIME
            )
        """))
        # El responsable viejo era un id de usuario y no se corresponde con
        # ningún nombre del equipo, así que las tareas existentes se quedan sin
        # asignar. Son dos clics volver a repartirlas, y es más honesto que
        # inventarse a quién iban.
        db.execute(text("""
            INSERT INTO tareas_equipo_new
                (id, texto, asignado_a, fecha_limite, prioridad, estado,
                 completada_en, avisada_en, created_at)
            SELECT id, texto, NULL, fecha_limite, prioridad, estado,
                   completada_en, avisada_en, created_at
            FROM tareas_equipo
        """))
        db.execute(text("DROP TABLE tareas_equipo"))
        db.execute(text("ALTER TABLE tareas_equipo_new RENAME TO tareas_equipo"))
        db.commit()
        logger.info("tareas_equipo migrada: el responsable pasa a ser un nombre")


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

# Rutas públicas: las únicas de la app que no exigen sesión. Van primero
# para que se vea de un vistazo que existen.
app.include_router(bienvenida.router)
app.include_router(webhooks.router)
app.include_router(auth.router)
app.include_router(scripts.router)
app.include_router(profile.router)
app.include_router(admin.router)
app.include_router(chatbot.router)
app.include_router(ideas.router)
app.include_router(editor.router)
app.include_router(biblioteca.router)
app.include_router(crm.router)
app.include_router(robert.router)


@app.exception_handler(303)
async def redirect_handler(_request: Request, exc: HTTPException):
    location = (exc.headers or {}).get("Location", "/login")
    return RedirectResponse(url=location, status_code=303)


@app.exception_handler(Exception)
async def generic_error_handler(_request: Request, exc: Exception):
    logger.error("Unhandled exception: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(status_code=500, content={"detail": str(exc)})
