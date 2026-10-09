"""La página de tareas de una colaboradora: /mis-tareas

Una sola pantalla, con su propia contraseña, fuera de la app. Quien entra ve
las tareas que llevan su nombre y nada más: puede marcarlas, anotar cómo va y
apuntarse alguna suelta.

Por qué no es una cuenta de usuario:

  · Ser administrador en esta app es verlo todo —el CRM, los alumnos, los
    resúmenes de las llamadas de venta, los ingresos—. Eso no se le puede dar
    a alguien que además trabaja para otros negocios.
  · Un rol nuevo obligaría a tocar la autenticación de una app con clientes
    pagando dentro, y ahí es donde se escapan los datos. Esto es una ruta
    aparte que sólo sabe leer y escribir filas con un nombre concreto: no hay
    forma de que se cruce con nada más, porque no sabe hacerlo.

La contraseña es corta a propósito, para que se pueda teclear en el móvil todos
los días. Lo que la respalda no es su longitud, sino que al otro lado no hay
nada que robar: una lista de recados. Aun así se limitan los intentos, porque
una contraseña corta sin límite de intentos sí se adivina.
"""
import logging
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import (ALGORITHM, ENV, SECRET_KEY, TAREAS_PASSWORD,
                        TAREAS_PERSONA)
from app.database import get_db
from app.models import TareaEquipo
from app.services.tareas_fijas import asegurar_semana, lunes_de

log = logging.getLogger(__name__)

router = APIRouter(prefix="/mis-tareas")
templates = Jinja2Templates(directory="app/templates")

# Nombre propio, distinto del `access_token` de la app. Son dos sesiones que no
# se tocan: con esta cookie no se entra a la app, y con la de la app no se entra
# aquí. Si compartieran nombre, una pisaría a la otra en el mismo navegador.
COOKIE = "panel_tareas"
HORAS = 12                       # se vuelve a pedir una vez al día

# Intentos fallidos por IP. En memoria a propósito: hay un solo proceso de
# uvicorn, y si se reinicia lo peor que pasa es que alguien recupere sus
# intentos. Guardarlo en la base de datos sería más ceremonia que provecho.
_fallos: dict[str, tuple[int, float]] = {}
TOPE = 8
CASTIGO = 15 * 60                # segundos


def _ip(request: Request) -> str:
    """La IP real, que detrás de nginx no es la de la conexión."""
    reenviada = request.headers.get("x-forwarded-for") or ""
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _bloqueada(ip: str) -> bool:
    veces, hasta = _fallos.get(ip, (0, 0.0))
    if veces >= TOPE and time.time() < hasta:
        return True
    if veces >= TOPE:            # ya cumplió el castigo
        _fallos.pop(ip, None)
    return False


def _activo() -> None:
    """Sin contraseña configurada esta página no existe."""
    if not TAREAS_PASSWORD:
        raise HTTPException(status_code=404)


def _vale(token: Optional[str]) -> bool:
    """¿Esta cookie es una sesión válida de ESTE panel?

    Se exige el claim `panel` con el nombre exacto. Un `access_token` de la app
    lleva `sub` y no `panel`, así que aunque alguien lo copiara aquí no serviría.
    """
    if not token:
        return False
    try:
        datos = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return False
    return datos.get("panel") == TAREAS_PERSONA


def _nueva_cookie() -> str:
    return jwt.encode(
        {"panel": TAREAS_PERSONA,
         "exp": datetime.now(timezone.utc) + timedelta(hours=HORAS)},
        SECRET_KEY, algorithm=ALGORITHM)


def _mia(db: Session, tid: int) -> TareaEquipo:
    """La tarea, sólo si lleva su nombre. Si no, no existe.

    Es el único cerrojo de este módulo y por eso pasa por aquí TODO lo que
    modifica algo. 404 y no 403: que no se pueda ni averiguar qué ids hay.
    """
    t = db.get(TareaEquipo, tid)
    if t is None or t.asignado_a != TAREAS_PERSONA:
        raise HTTPException(status_code=404, detail="No encontrada")
    return t


def _bloque(t: TareaEquipo, lunes: date) -> str:
    """En cuál de los tres grupos de la página va. Un solo sitio lo decide.

    «archivo» es lo hecho en semanas anteriores: no se le enseña, porque su
    página es la de esta semana. El registro entero lo ve Robert en admin.
    """
    if t.estado == "hecha":
        if t.completada_en and lunes_de(t.completada_en.date()) == lunes:
            return "hechas"
        return "archivo"
    if t.fija_id is not None and t.semana == lunes:
        return "fijas"
    return "puntuales"


def _json(t: TareaEquipo, lunes: Optional[date] = None) -> dict:
    lunes = lunes or lunes_de(date.today())
    return {
        "id": t.id,
        "texto": t.texto,
        "fija": t.fija_id is not None,
        "bloque": _bloque(t, lunes),
        "fecha_corta": t.fecha_limite.strftime("%d/%m") if t.fecha_limite else None,
        "dia": _DIAS[t.fecha_limite.weekday()] if t.fecha_limite else None,
        "urgente": t.prioridad == "urgente",
        "vencida": t.vencida,
        "hoy": t.es_hoy,
        "estado": t.estado,
        "notas": t.notas or "",
        "hecha_el": t.completada_en.strftime("%d/%m") if t.completada_en else None,
        "enlace": t.enlace or None,
        "enlace_icono": t.enlace_icono or "enlace",
        "enlace_nombre": _NOMBRES.get(t.enlace_icono or "", "Abrir el enlace"),
    }


# Cómo se llama cada sitio en el botón. El nombre va escrito al lado del icono:
# un dibujo de 20px no se reconoce siempre, y menos en un móvil al sol.
_NOMBRES = {
    "gdoc": "Abrir el documento",
    "metricool": "Abrir Metricool",
    "whatsapp": "Abrir WhatsApp",
    "enlace": "Abrir el enlace",
}


_DIAS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


# ── Entrar y salir ────────────────────────────────────────────────────────
# Las rutas con nombre fijo van ANTES que las que llevan un {tid}, para que el
# comodín no se trague «entrar» ni «salir».

@router.post("/entrar")
async def entrar(request: Request, clave: str = Form("")):
    _activo()
    ip = _ip(request)
    if _bloqueada(ip):
        return _pantalla_clave(request, "Demasiados intentos. Prueba dentro de un rato.")

    if not _coincide(clave, TAREAS_PASSWORD):
        veces, _ = _fallos.get(ip, (0, 0.0))
        _fallos[ip] = (veces + 1, time.time() + CASTIGO)
        log.warning("Panel de tareas: contraseña fallida desde %s", ip)
        return _pantalla_clave(request, "Esa contraseña no es.")

    _fallos.pop(ip, None)
    r = RedirectResponse(url="/mis-tareas", status_code=303)
    # `secure` en producción, donde todo va por HTTPS. En local iría por http y
    # el navegador se guardaría la cookie sin mandarla nunca: la contraseña
    # entraría bien y la página volvería a pedirla, en bucle y sin decir por qué.
    r.set_cookie(COOKIE, _nueva_cookie(), max_age=HORAS * 3600,
                 httponly=True, samesite="lax", secure=ENV != "development")
    return r


@router.post("/salir")
async def salir():
    _activo()
    r = RedirectResponse(url="/mis-tareas", status_code=303)
    r.delete_cookie(COOKIE)
    return r


def _coincide(escrito: str, bueno: str) -> bool:
    """¿Es esta la contraseña? Comparación en tiempo constante, sobre BYTES.

    Sobre texto no: `secrets.compare_digest` lanza una excepción en cuanto una
    de las dos cadenas trae un carácter que no sea ASCII, y lo que se compara
    aquí lo teclea una persona en un móvil. Una tilde, una ñ o una comilla
    curva del teclado tiraban la página entera con un error en crudo en vez de
    decir simplemente que la contraseña no es.

    De paso se quitan los espacios de los extremos, incluido el espacio duro
    que cuelan algunos teclados y correctores al pegar texto.
    """
    limpio = (escrito or "").strip().strip("\u00a0").strip()
    return secrets.compare_digest(limpio.encode("utf-8"), (bueno or "").encode("utf-8"))


def _pantalla_clave(request: Request, aviso: str = "") -> HTMLResponse:
    return templates.TemplateResponse(
        "mis_tareas_clave.html",
        {"request": request, "persona": TAREAS_PERSONA, "aviso": aviso},
        status_code=200 if not aviso else 401)


# ── La página ─────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def pagina(request: Request,
                 panel_tareas: Optional[str] = Cookie(default=None),
                 db: Session = Depends(get_db)):
    _activo()
    if not _vale(panel_tareas):
        return _pantalla_clave(request)

    hoy = date.today()
    lunes = lunes_de(hoy)
    # Las fijas de esta semana se crean aquí, al abrir. Si ya están, no hace nada.
    asegurar_semana(db, TAREAS_PERSONA, hoy)

    todas = (db.query(TareaEquipo)
               .filter(TareaEquipo.asignado_a == TAREAS_PERSONA)
               .order_by(TareaEquipo.fecha_limite.is_(None),
                         TareaEquipo.fecha_limite,
                         TareaEquipo.prioridad != "urgente",
                         TareaEquipo.created_at)
               .all())

    grupos = {"fijas": [], "puntuales": [], "hechas": [], "archivo": []}
    for t in todas:
        datos = _json(t, lunes)
        grupos[datos["bloque"]].append(datos)
    fijas, puntuales = grupos["fijas"], grupos["puntuales"]
    # Lo último marcado, arriba.
    hechas = sorted(grupos["hechas"], key=lambda x: x["id"], reverse=True)

    # Las fijas que todavía no han empezado. Sin esto la página miente por
    # omisión: una tarea de los lunes dada de alta un viernes no existe en
    # ninguna parte de la pantalla hasta el lunes, y quien la creó da por hecho
    # que no se guardó. Se enseñan apagadas, sin círculo que marcar.
    proximas = _proximas(db, lunes)
    domingo = lunes + timedelta(days=6)
    if lunes.month == domingo.month:
        rotulo = f"Semana del {lunes.day} al {domingo.day} de {_MESES[domingo.month - 1]}"
    else:
        rotulo = (f"Semana del {lunes.day} de {_MESES[lunes.month - 1]} "
                  f"al {domingo.day} de {_MESES[domingo.month - 1]}")

    return templates.TemplateResponse("mis_tareas.html", {
        "request": request, "persona": TAREAS_PERSONA, "semana": rotulo,
        "fijas": fijas, "puntuales": puntuales, "hechas": hechas,
        "proximas": proximas,
        "pendientes": len(fijas) + len(puntuales),
    })


def _proximas(db: Session, lunes: date) -> list:
    """Fijas suyas que aún no tienen copia esta semana, y por tanto no se ven.

    Son las de un día concreto que se dieron de alta cuando ese día ya había
    pasado: no se crean para esta semana para que no salgan vencidas de
    nacimiento. Las diarias nunca entran aquí, porque la de hoy ya está.
    """
    from app.models import TareaFija

    fijas = (db.query(TareaFija)
               .filter(TareaFija.activa.is_(True),
                       TareaFija.asignado_a == TAREAS_PERSONA,
                       TareaFija.cada_dia.is_(False),
                       TareaFija.dia_semana.isnot(None))
               .order_by(TareaFija.dia_semana, TareaFija.id).all())
    if not fijas:
        return []

    con_copia = {fid for (fid,) in
                 db.query(TareaEquipo.fija_id)
                   .filter(TareaEquipo.semana == lunes,
                           TareaEquipo.fija_id.isnot(None)).all()}

    return [{
        "texto": f.texto,
        "dia": TareaFija.DIAS[f.dia_semana].capitalize(),
        "enlace": f.enlace or None,
        "enlace_icono": f.enlace_icono or "enlace",
        "enlace_nombre": _NOMBRES.get(f.enlace_icono or "", "Abrir el enlace"),
    } for f in fijas if f.id not in con_copia]


# ── Lo que puede hacer: apuntar, marcar y anotar ──────────────────────────

@router.post("/nueva")
async def nueva(texto: str = Form(""),
                panel_tareas: Optional[str] = Cookie(default=None),
                db: Session = Depends(get_db)):
    """Una tarea suelta que se apunta ella. Siempre a su nombre y sin fecha.

    El texto NO pasa por el analizador de frases del panel del equipo: ahí un
    «@robert» reasignaría la tarea a otra persona, y desde aquí nadie debería
    poder escribir en la lista de otro.
    """
    _activo()
    if not _vale(panel_tareas):
        raise HTTPException(status_code=401, detail="Vuelve a entrar")

    frase = (texto or "").strip()
    if not frase:
        raise HTTPException(status_code=422, detail="Está vacía")

    t = TareaEquipo(texto=frase[:300], asignado_a=TAREAS_PERSONA, prioridad="normal")
    db.add(t)
    db.commit()
    db.refresh(t)

    # La fila la monta el servidor con el mismo macro que usa la página. Si la
    # montara el JS habría dos versiones del mismo HTML.
    macro = templates.get_template("_mis_tareas_fila.html").module
    datos = _json(t)
    return JSONResponse({"tarea": datos, "html": str(macro.fila(datos))})


@router.post("/{tid}/estado")
async def estado(tid: int,
                 panel_tareas: Optional[str] = Cookie(default=None),
                 db: Session = Depends(get_db)):
    _activo()
    if not _vale(panel_tareas):
        raise HTTPException(status_code=401, detail="Vuelve a entrar")
    t = _mia(db, tid)
    if t.estado == "hecha":
        t.estado, t.completada_en = "pendiente", None
    else:
        t.estado, t.completada_en = "hecha", datetime.utcnow()
    db.commit()
    db.refresh(t)
    return JSONResponse(_json(t))


@router.post("/{tid}/nota")
async def nota(tid: int, valor: str = Form(""),
               panel_tareas: Optional[str] = Cookie(default=None),
               db: Session = Depends(get_db)):
    _activo()
    if not _vale(panel_tareas):
        raise HTTPException(status_code=401, detail="Vuelve a entrar")
    t = _mia(db, tid)
    t.notas = (valor or "").strip()[:5000] or None
    db.commit()
    return JSONResponse({"guardado": True})
