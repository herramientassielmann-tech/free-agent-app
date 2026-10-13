"""La página de bienvenida: de agendar la llamada a estar dentro.

Son las PRIMERAS rutas públicas de la app. Todo lo demás pasa por
`get_current_user`, que ante cualquier fallo lanza un 303 a /login; aquí eso no
sirve, porque quien abre esto todavía no tiene cuenta. La identidad la da el
token del enlace, que es largo, aleatorio y caduca.

Orden de los bloques: primero cobrar, luego firmar, y sólo entonces se abren los
accesos. No se entrega el producto antes de cobrar. El desbloqueo a mano existe
porque a veces el cobro va por transferencia y el alumno está delante en la
llamada.
"""
import hashlib
import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password
from app.config import (
    ALGORITHM, APP_URL, CALENDLY_ONBOARDING_URL, ENV, SECRET_KEY,
    SKOOL_INVITE_URL, STRIPE_PAYMENT_LINK, VIDEO_ACADEMIA_URL,
    VIDEO_HERRAMIENTA_URL,
)
from app.database import get_db
from app.models import Alta, FirmaContrato, User

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Sube cada vez que cambie el TEXTO del contrato. Se guarda con cada firma:
# sin esto no se podría saber qué versión aceptó cada persona, y dos alumnos
# podrían haber firmado documentos distintos sin que quede rastro.
#   v1.0 — 20 cláusulas, con arbitraje y compromiso de vídeos semanales
#   v1.1 — fuera las cláusulas 6 y 20; la 18 pasa a cubrir la jurisdicción
#   v1.2 — la ley aplicable deja de estar pendiente: Florida (EE. UU.)
VERSION_CONTRATO = "v1.2"

# Los datos de la empresa y las dos decisiones legales pendientes. Van aquí y no
# en .env porque forman parte del texto del contrato, no de la configuración del
# servidor: cambiarlos cambia el documento, y eso debe verse en un commit.
EMPRESA = {
    "empresa_titular": "Robert Sielmann",
    "empresa_domicilio": "[pendiente]",
    "empresa_nif": "[pendiente]",
    "empresa_firmante": "Robert Sielmann",
    "contacto": "herramientassielmann@gmail.com",
    # Se escribe tal cual va a leerse detrás de «se rige por las leyes de …»,
    # así que sin artículo delante: «Florida (EE. UU.)», no «el Estado de
    # Florida» —saldría «de el Estado de Florida»—.
    "ley": "Florida (EE. UU.)",
}

# Lo que firma aparte. Son los dos puntos que de verdad se discuten cuando
# alguien reclama: que no se le prometió ningún resultado y que no hay
# devolución. Una cláusula de no devolución enterrada en la letra pequeña se
# anula; firmada expresamente, aguanta.
RECONOCIMIENTOS = [
    ("resultados",
     "He leído y comprendo la cláusula 5. Entiendo que <b>FA Academy no me "
     "garantiza ningún resultado</b> y que no he contratado el Programa sobre la "
     "base de promesa alguna de ingresos o de captación de clientes."),
    ("devoluciones",
     "He leído y comprendo la cláusula 6. Entiendo que <b>las cantidades abonadas "
     "no son reembolsables</b>, sin perjuicio de los derechos que la ley imperativa "
     "me reconozca, y que renunciar a continuar no me exime de los plazos pendientes."),
]


# ── Utilidades ───────────────────────────────────────────────────────────────

def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


# Sin O/0 ni I/1/L: esto se dicta por teléfono y se teclea en un móvil, y esas
# cuatro son las que siempre se escriben mal.
_ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def nuevo_codigo(db: Session) -> str:
    """Un código corto, libre, para dárselo a una persona concreta."""
    from app.models import Alta
    for _ in range(40):
        c = "".join(secrets.choice(_ALFABETO) for _ in range(8))
        if not db.query(Alta.id).filter(Alta.codigo == c).first():
            return c
    # Con 31^8 combinaciones esto no pasa; si pasara, mejor fallar que repetir.
    raise RuntimeError("No se pudo generar un código libre")


# La sesión del alumno. Va en cookie y NO en la URL: una URL se reenvía por
# WhatsApp sin pensarlo, y entonces el que la recibe entra. El código se le da
# a una persona, y la cookie se queda en SU móvil.
COOKIE_ALUMNO = "alta_sesion"
HORAS_SESION = 72

_fallos_codigo: dict[str, tuple[int, float]] = {}
TOPE_CODIGO = 10
CASTIGO_CODIGO = 15 * 60


def _ficha_sesion(alta: "Alta") -> str:
    return jwt.encode(
        {"alta": alta.id,
         "exp": datetime.now(timezone.utc) + timedelta(hours=HORAS_SESION)},
        SECRET_KEY, algorithm=ALGORITHM)


def _alta_sesion(request: Request, db: Session) -> "Alta":
    """El alta de quien está navegando, sacada de la cookie. 404 si no hay."""
    ficha = request.cookies.get(COOKIE_ALUMNO)
    if not ficha:
        raise HTTPException(status_code=404, detail="No encontrado")
    try:
        datos = jwt.decode(ficha, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=404, detail="No encontrado")
    alta = db.get(Alta, datos.get("alta") or 0)
    if alta is None:
        raise HTTPException(status_code=404, detail="No encontrado")
    return alta


def caducidad() -> datetime:
    return datetime.utcnow() + timedelta(days=14)


def _alta(token: str, db: Session) -> Alta:
    """Resuelve el alta por su token, o 404.

    Siempre 404, nunca 403 ni 410: un mensaje distinto según el motivo le diría
    a quien pruebe tokens al azar cuándo ha acertado uno que existe.
    """
    if not token or len(token) < 20:
        raise HTTPException(status_code=404, detail="No encontrado")
    fila = db.query(Alta).filter(Alta.token == token).first()
    # Sobre bytes y no sobre texto: `compare_digest` lanza con cualquier
    # carácter no ASCII, y `token` llega de la URL, donde entra cualquier cosa.
    if fila is None or not secrets.compare_digest(
            (fila.token or "").encode("utf-8"), (token or "").encode("utf-8")):
        raise HTTPException(status_code=404, detail="No encontrado")
    if fila.token_expira < datetime.utcnow():
        raise HTTPException(status_code=404, detail="No encontrado")
    return fila


def _ip(request: Request) -> str:
    """La IP real del visitante. Detrás de nginx, request.client es 127.0.0.1."""
    reenviada = request.headers.get("x-forwarded-for", "")
    if reenviada:
        return reenviada.split(",")[0].strip()[:60]
    return (request.client.host if request.client else "")[:60]


def _documento(alta: Alta, *, firma: Optional[FirmaContrato] = None,
               datos: Optional[dict] = None) -> dict:
    """Arma el diccionario con el que se pinta el contrato.

    Se usa dos veces: para que lo lea antes de firmar (sin firmante) y para
    congelar el documento ya ejecutado.
    """
    marcados = set()
    if firma:
        try:
            marcados = set(json.loads(firma.reconocimientos))
        except Exception:
            marcados = set()
    elif datos:
        marcados = set(datos.get("reconocimientos", []))

    d = dict(EMPRESA)
    d.update({
        "ref": f"FA-{alta.id}",
        "version": VERSION_CONTRATO,
        "alumno_nombre": (firma.nombre_firmante if firma else alta.nombre),
        "alumno_documento": (firma.documento_id if firma else (datos or {}).get("documento", "")) or "",
        "alumno_domicilio": (firma.domicilio if firma else (datos or {}).get("domicilio", "")) or "",
        "alumno_email": alta.email,
        "modalidad": (datos or {}).get("modalidad") or "unico",
        "imagen": bool((datos or {}).get("imagen")),
        "reconocimientos": [
            {"texto": texto, "marcado": clave in marcados}
            for clave, texto in RECONOCIMIENTOS
        ],
        "consentimiento": bool(firma.consentimiento_electronico if firma else (datos or {}).get("consentimiento")),
        "consentimiento_en": (firma.consentimiento_en.strftime("%d/%m/%Y %H:%M UTC")
                              if firma and firma.consentimiento_en else None),
        "firmante": firma.nombre_firmante if firma else None,
        "firmado_en": firma.firmado_en.strftime("%d/%m/%Y a las %H:%M UTC") if firma else None,
        "firmado_fecha": firma.firmado_en.strftime("%d/%m/%Y") if firma else None,
        "ip": firma.ip if firma else None,
        "user_agent": (firma.user_agent or "")[:120] if firma else None,
        "huella": firma.huella_documento if firma else None,
    })
    return d


def _huella(html: str) -> str:
    return hashlib.sha256(html.encode("utf-8")).hexdigest()


def _pasos(alta: Alta) -> list:
    """Los cuatro bloques. Cada uno se abre al terminar el anterior.

    El orden no es decorativo. El contrato va primero porque es lo único que no
    puede quedarse sin hacer. La llamada con Robert antes que la herramienta
    porque en esa llamada se decide qué va a grabar, y sin eso la herramienta es
    un generador de guiones que no sabe de qué. Y el vídeo antes del acceso
    porque quien entra sin saber usarla no vuelve.
    """
    return [
        {"n": 1, "clave": "contrato", "titulo": "Firma el contrato",
         "hecho": bool(alta.contrato_firmado_en), "bloqueado": False, "listo": True},
        {"n": 2, "clave": "onboarding", "titulo": "Onboarding con Robert",
         "hecho": bool(alta.onboarding_agendado_en),
         "bloqueado": not alta.contrato_firmado_en,
         "listo": bool(CALENDLY_ONBOARDING_URL)},
        {"n": 3, "clave": "video", "titulo": "Cómo se usa la herramienta",
         "hecho": bool(alta.video_visto_en),
         "bloqueado": not alta.onboarding_agendado_en,
         "listo": bool(VIDEO_HERRAMIENTA_URL)},
        {"n": 4, "clave": "cuenta", "titulo": "Entra en la herramienta",
         "hecho": bool(alta.cuenta_creada_en),
         "bloqueado": not alta.video_visto_en, "listo": True},
    ]


def _video_incrustado(url: Optional[str]) -> Optional[str]:
    """La dirección para incrustar, a partir del enlace que se pega tal cual.

    Se pega el enlace normal de YouTube o de Loom —el que sale al darle a
    compartir— y aquí se traduce. Pedirle a nadie la URL de incrustar es pedir
    que se equivoque.
    """
    if not url:
        return None
    u = url.strip()
    m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{6,})", u)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    m = re.search(r"loom\.com/(?:share|embed)/([A-Za-z0-9]{10,})", u)
    if m:
        return f"https://www.loom.com/embed/{m.group(1)}"
    return None


# ── La página ────────────────────────────────────────────────────────────────

def _pagina(request: Request, alta: Alta, error: str = "") -> HTMLResponse:
    return templates.TemplateResponse("empieza.html", {
        "request": request,
        "alta": alta,
        "pasos": _pasos(alta),
        "video": _video_incrustado(VIDEO_HERRAMIENTA_URL),
        "error_cuenta": error,
    })


@router.get("/empieza", response_class=HTMLResponse)
async def empieza(request: Request, db: Session = Depends(get_db)):
    """La única dirección que se reparte. Sin código válido, sólo la puerta."""
    try:
        alta = _alta_sesion(request, db)
    except HTTPException:
        return templates.TemplateResponse("empieza_codigo.html", {"request": request})
    return _pagina(request, alta)


@router.post("/empieza/entrar")
async def empieza_entrar(request: Request, codigo: str = Form(""),
                         db: Session = Depends(get_db)):
    ip = _ip(request)
    veces, hasta = _fallos_codigo.get(ip, (0, 0.0))
    if veces >= TOPE_CODIGO and time.time() < hasta:
        return templates.TemplateResponse(
            "empieza_codigo.html",
            {"request": request, "aviso": "Demasiados intentos. Prueba dentro de un rato."},
            status_code=429)

    limpio = re.sub(r"[^A-Za-z0-9]", "", codigo or "").upper()
    alta = (db.query(Alta).filter(Alta.codigo == limpio).first() if limpio else None)
    if alta is None:
        _fallos_codigo[ip] = (veces + 1, time.time() + CASTIGO_CODIGO)
        log.warning("Código de acceso fallido desde %s", ip)
        return templates.TemplateResponse(
            "empieza_codigo.html",
            {"request": request, "aviso": "Ese código no es. Revísalo o escríbenos."},
            status_code=401)

    _fallos_codigo.pop(ip, None)
    r = RedirectResponse(url="/empieza", status_code=303)
    r.set_cookie(COOKIE_ALUMNO, _ficha_sesion(alta), max_age=HORAS_SESION * 3600,
                 httponly=True, samesite="lax", secure=ENV != "development")
    return r


@router.post("/empieza/salir")
async def empieza_salir():
    r = RedirectResponse(url="/empieza", status_code=303)
    r.delete_cookie(COOKIE_ALUMNO)
    return r


@router.post("/empieza/video")
async def empieza_video(request: Request, db: Session = Depends(get_db)):
    """«Ya lo he visto». Es lo que abre el último paso."""
    alta = _alta_sesion(request, db)
    if not alta.onboarding_agendado_en:
        raise HTTPException(status_code=404, detail="No encontrado")
    if not alta.video_visto_en:
        alta.video_visto_en = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/empieza", status_code=303)


@router.get("/bienvenida/{token}", response_class=HTMLResponse)
async def portada(token: str, db: Session = Depends(get_db)):
    """Los enlaces largos de antes siguen funcionando: dejan la cookie puesta
    y mandan a /empieza, para que el token no se quede en la barra del navegador."""
    alta = _alta(token, db)
    r = RedirectResponse(url="/empieza", status_code=303)
    r.set_cookie(COOKIE_ALUMNO, _ficha_sesion(alta), max_age=HORAS_SESION * 3600,
                 httponly=True, samesite="lax", secure=ENV != "development")
    return r


@router.get("/bienvenida/{token}/pagar")
async def pagar(token: str, db: Session = Depends(get_db)):
    alta = _alta(token, db)
    if not STRIPE_PAYMENT_LINK:
        raise HTTPException(status_code=404, detail="No encontrado")
    # client_reference_id es lo que permite al webhook saber de quién es el pago.
    destino = (f"{STRIPE_PAYMENT_LINK}?client_reference_id=alta_{alta.id}"
               f"&prefilled_email={alta.email}")
    return RedirectResponse(url=destino, status_code=302)


@router.get("/empieza/academia")
async def skool(request: Request, db: Session = Depends(get_db)):
    alta = _alta_sesion(request, db)
    if not alta.contrato_firmado_en or not SKOOL_INVITE_URL:
        raise HTTPException(status_code=404, detail="No encontrado")
    if not alta.skool_abierto_en:
        alta.skool_abierto_en = datetime.utcnow()
        db.commit()
    return RedirectResponse(url=SKOOL_INVITE_URL, status_code=302)


@router.get("/empieza/onboarding")
async def onboarding(request: Request, db: Session = Depends(get_db)):
    alta = _alta_sesion(request, db)
    # La cascada, también aquí: no basta con que el botón no se vea en la
    # página; si alguien llega a la URL directamente, tampoco pasa.
    if not alta.contrato_firmado_en or not CALENDLY_ONBOARDING_URL:
        raise HTTPException(status_code=404, detail="No encontrado")
    if not alta.onboarding_agendado_en:
        alta.onboarding_agendado_en = datetime.utcnow()
        db.commit()
    sep = "&" if "?" in CALENDLY_ONBOARDING_URL else "?"
    destino = f"{CALENDLY_ONBOARDING_URL}{sep}name={alta.nombre}&email={alta.email}"
    return RedirectResponse(url=destino, status_code=302)


# ── Contrato ─────────────────────────────────────────────────────────────────


def _huecos_legales() -> list:
    """Los datos del contrato que siguen sin rellenar.

    Existe para que no se pueda firmar a medias. Un contrato que dice «se rige
    por las leyes de [pendiente: estado aplicable]» no es un contrato a medio
    hacer: es un contrato con un agujero en la clausula que decide dónde se
    reclama, y firmado vale menos que no tener nada. Mejor que no se pueda
    abrir a que alguien lo firme así.
    """
    return sorted(k for k, v in EMPRESA.items() if "[pendiente" in str(v))



@router.get("/empieza/contrato", response_class=HTMLResponse)
async def contrato(request: Request, db: Session = Depends(get_db)):
    alta = _alta_sesion(request, db)
    firma = alta.firma
    # Si ya está firmado se enseña siempre: es su copia, y se guardó con los
    # datos que hubiera en ese momento. Lo que se corta es firmar de nuevo.
    faltan = _huecos_legales()
    if faltan and firma is None:
        # La página no dice qué falta —eso es cosa nuestra, no del alumno—, así
        # que queda en el registro del servidor para que se pueda ver por qué.
        log.warning(
            "Contrato no firmable: faltan %s en EMPRESA (app/routers/bienvenida.py). "
            "Alta %s quedó esperando.", ", ".join(faltan), alta.id)
        return templates.TemplateResponse("contrato_pendiente.html", {
            "request": request, "alta": alta, "faltan": faltan,
        }, status_code=503)
    return templates.TemplateResponse("contrato_firma.html", {
        "request": request,
        "alta": alta,
        "firma": firma,
        "d": _documento(alta, firma=firma),
        "reconocimientos": RECONOCIMIENTOS,
    })


@router.post("/empieza/firmar")
async def firmar(
    request: Request,
    db: Session = Depends(get_db),
    nombre_firmante: str = Form(""),
    documento: str = Form(""),
    domicilio: str = Form(""),
    modalidad: str = Form("unico"),
    consentimiento: Optional[str] = Form(None),
    imagen: Optional[str] = Form(None),
    r_resultados: Optional[str] = Form(None),
    r_devoluciones: Optional[str] = Form(None),
):
    alta = _alta_sesion(request, db)
    if alta.firma is not None:
        return RedirectResponse(url="/empieza/contrato", status_code=303)
    # La misma puerta que en el GET: sin esto, un formulario ya cargado antes de
    # que faltaran datos podría enviarse igual.
    if _huecos_legales():
        return RedirectResponse(url="/empieza/contrato", status_code=303)

    marcados = [c for c, v in (("resultados", r_resultados),
                               ("devoluciones", r_devoluciones)) if v]

    def volver(error: str):
        return templates.TemplateResponse("contrato_firma.html", {
            "request": request, "alta": alta, "firma": None,
            "d": _documento(alta, datos={"documento": documento, "domicilio": domicilio,
                                         "modalidad": modalidad, "imagen": bool(imagen),
                                         "consentimiento": bool(consentimiento),
                                         "reconocimientos": marcados}),
            "reconocimientos": RECONOCIMIENTOS,
            "error": error,
            "previo": {"nombre_firmante": nombre_firmante, "documento": documento,
                       "domicilio": domicilio, "modalidad": modalidad,
                       "imagen": bool(imagen), "consentimiento": bool(consentimiento),
                       "marcados": marcados},
        }, status_code=400)

    # El consentimiento electrónico no es una casilla más: sin él la firma es
    # atacable, así que se valida antes que nada.
    if not consentimiento:
        return volver("Para firmar en electrónico tienes que dar tu consentimiento.")
    if len(marcados) < len(RECONOCIMIENTOS):
        return volver("Tienes que marcar los dos reconocimientos para poder firmar.")
    if len(nombre_firmante.strip()) < 5:
        return volver("Escribe tu nombre y apellidos completos para firmar.")

    ahora = datetime.utcnow()
    firma = FirmaContrato(
        alta_id=alta.id,
        nombre_firmante=nombre_firmante.strip()[:150],
        documento_id=documento.strip()[:60] or None,
        domicilio=domicilio.strip()[:300] or None,
        consentimiento_electronico=True,
        consentimiento_en=ahora,
        reconocimientos=json.dumps(marcados),
        ip=_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400],
        huella_documento="",
        version_contrato=VERSION_CONTRATO,
        html_firmado="",
        firmado_en=ahora,
    )

    # Se congela el documento ya ejecutado y se sella con su huella. Sin esto se
    # podría probar que firmó, pero no QUÉ firmó.
    d = _documento(alta, firma=firma, datos={"modalidad": modalidad, "imagen": bool(imagen)})
    d["modalidad"] = modalidad
    d["imagen"] = bool(imagen)
    html = templates.get_template("_contrato_cuerpo.html").render(d=d)
    firma.huella_documento = _huella(html)
    firma.html_firmado = html

    alta.contrato_firmado_en = ahora
    db.add(firma)
    db.commit()

    _mandar_copia(alta, firma)
    return RedirectResponse(url="/empieza/contrato", status_code=303)


def _mandar_copia(alta: Alta, firma: FirmaContrato) -> None:
    """Le manda su copia. La conservación del documento es uno de los cinco
    requisitos de la E-SIGN Act, y un correo con el enlace es la forma más
    sencilla de cumplirlo."""
    try:
        from app.services.email import enviar, esta_configurado
        if not esta_configurado():
            return
        enlace = f"{APP_URL}/bienvenida/{alta.token}/contrato"
        enviar(
            alta.email,
            "Tu contrato firmado — FA Academy",
            f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;
                 font-size:15px;color:#16202C;line-height:1.6;max-width:520px">
              <p>Hola {alta.nombre.split()[0] if alta.nombre else ''},</p>
              <p>Queda constancia de que has firmado el contrato de Free Agent Academy
              el {firma.firmado_en.strftime('%d/%m/%Y a las %H:%M UTC')}.</p>
              <p><a href="{enlace}" style="color:#0A6FD4">Consulta y descarga tu copia aquí</a>.
              Puedes pedirnos una copia en papel cuando quieras, sin coste.</p>
              <p style="font-size:12px;color:#5A6874">Huella del documento: {firma.huella_documento}</p>
            </div>""",
            f"Has firmado el contrato de Free Agent Academy el "
            f"{firma.firmado_en.strftime('%d/%m/%Y %H:%M UTC')}.\nTu copia: {enlace}\n",
        )
    except Exception:
        pass   # Un correo que no sale no puede tumbar una firma ya válida.


# ── Cuenta ───────────────────────────────────────────────────────────────────

@router.post("/empieza/cuenta")
async def crear_cuenta(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
):
    alta = _alta_sesion(request, db)

    def volver(error: str):
        return _pagina(request, alta, error)
    if False:
        return templates.TemplateResponse("bienvenida.html", {
            "request": request, "alta": alta, "pasos": _pasos(alta),
            "abiertos": alta.accesos_abiertos, "error_cuenta": error,
            "video": _video_incrustado(VIDEO_ACADEMIA_URL),
            "email_previo": email,
        }, status_code=400)

    if not alta.video_visto_en:
        return volver("Todavía no podemos abrirte la cuenta: falta confirmar el pago.")
    if alta.user_id:
        return volver("Tu cuenta ya está creada. Entra desde la página de acceso.")

    email = (email or "").strip().lower()
    if "@" not in email or len(email) < 6:
        return volver("Revisa el correo: no parece válido.")
    if len(password) < 8:
        return volver("La contraseña tiene que tener al menos 8 caracteres.")
    if password != password2:
        return volver("Las dos contraseñas no coinciden.")
    if db.query(User).filter(User.email == email).first():
        return volver("Ya existe una cuenta con ese correo. Usa otro o avísanos.")

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=alta.nombre.strip()[:100],
        is_admin=False,
        is_active=True,
        monthly_limit=None,          # sin límite de guiones
        must_change_password=False,  # la eligió él: no hay contraseña temporal
        temp_password=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    alta.user_id = user.id
    alta.cuenta_creada_en = datetime.utcnow()
    db.commit()

    # Entra directo: pedirle que inicie sesión justo después de elegir la
    # contraseña es un paso de más en el momento más frágil.
    respuesta = RedirectResponse(url="/", status_code=303)
    respuesta.set_cookie(
        key="access_token",
        value=create_access_token({"sub": str(user.id), "is_admin": False}),
        httponly=True,
        max_age=60 * 60 * 8,
        samesite="lax",
    )
    return respuesta
