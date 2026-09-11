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
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password
from app.config import (
    APP_URL, CALENDLY_ONBOARDING_URL, SKOOL_INVITE_URL, STRIPE_PAYMENT_LINK,
)
from app.database import get_db
from app.models import Alta, FirmaContrato, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VERSION_CONTRATO = "v1.0"

# Los datos de la empresa y las dos decisiones legales pendientes. Van aquí y no
# en .env porque forman parte del texto del contrato, no de la configuración del
# servidor: cambiarlos cambia el documento, y eso debe verse en un commit.
EMPRESA = {
    "empresa_titular": "Robert Sielmann",
    "empresa_domicilio": "[pendiente]",
    "empresa_nif": "[pendiente]",
    "empresa_firmante": "Robert Sielmann",
    "contacto": "herramientassielmann@gmail.com",
    "ley": "[pendiente: estado aplicable]",
    "arbitraje": "[pendiente: institución arbitral]",
}

# Las cuatro cosas que firma aparte. Son las que sostienen el resto del contrato:
# una cláusula de no devolución enterrada en la letra pequeña se anula; firmada
# expresamente, aguanta.
RECONOCIMIENTOS = [
    ("resultados",
     "He leído y comprendo la cláusula 5. Entiendo que <b>FA Academy no me "
     "garantiza ningún resultado</b> y que no he contratado el Programa sobre la "
     "base de promesa alguna de ingresos o de captación de clientes."),
    ("devoluciones",
     "He leído y comprendo la cláusula 7. Entiendo que <b>las cantidades abonadas "
     "no son reembolsables</b>, sin perjuicio de los derechos que la ley imperativa "
     "me reconozca, y que renunciar a continuar no me exime de los plazos pendientes."),
    ("compromiso",
     "He leído y comprendo la cláusula 6. Entiendo que el Programa <b>exige de mí "
     "un mínimo de dos vídeos semanales</b> y la aplicación de las indicaciones del "
     "equipo, y que su incumplimiento afecta al aprovechamiento de la formación."),
    ("arbitraje",
     "He leído y comprendo la cláusula 20. Entiendo que las controversias se "
     "resolverán mediante <b>arbitraje individual</b> y que renuncio a participar "
     "en acciones colectivas y al juicio con jurado."),
]


# ── Utilidades ───────────────────────────────────────────────────────────────

def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


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
    if fila is None or not secrets.compare_digest(fila.token, token):
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
    """Los cinco bloques y su estado. El orden es el del cierre en la llamada."""
    abiertos = alta.accesos_abiertos
    return [
        {"n": 1, "clave": "pago", "titulo": "Completa tu pago",
         "hecho": bool(alta.pagado_en), "bloqueado": False,
         "listo": bool(STRIPE_PAYMENT_LINK)},
        {"n": 2, "clave": "contrato", "titulo": "Firma el contrato",
         "hecho": bool(alta.contrato_firmado_en), "bloqueado": False, "listo": True},
        {"n": 3, "clave": "cuenta", "titulo": "Crea tu cuenta en la herramienta",
         "hecho": bool(alta.cuenta_creada_en), "bloqueado": not abiertos, "listo": True},
        {"n": 4, "clave": "skool", "titulo": "Entra en Skool",
         "hecho": bool(alta.skool_abierto_en), "bloqueado": not abiertos,
         "listo": bool(SKOOL_INVITE_URL)},
        {"n": 5, "clave": "onboarding", "titulo": "Agenda tu llamada de onboarding",
         "hecho": bool(alta.onboarding_agendado_en), "bloqueado": not abiertos,
         "listo": bool(CALENDLY_ONBOARDING_URL)},
    ]


# ── La página ────────────────────────────────────────────────────────────────

@router.get("/bienvenida/{token}", response_class=HTMLResponse)
async def portada(token: str, request: Request, db: Session = Depends(get_db)):
    alta = _alta(token, db)
    return templates.TemplateResponse("bienvenida.html", {
        "request": request,
        "alta": alta,
        "pasos": _pasos(alta),
        "abiertos": alta.accesos_abiertos,
    })


@router.get("/bienvenida/{token}/pagar")
async def pagar(token: str, db: Session = Depends(get_db)):
    alta = _alta(token, db)
    if not STRIPE_PAYMENT_LINK:
        raise HTTPException(status_code=404, detail="No encontrado")
    # client_reference_id es lo que permite al webhook saber de quién es el pago.
    destino = (f"{STRIPE_PAYMENT_LINK}?client_reference_id=alta_{alta.id}"
               f"&prefilled_email={alta.email}")
    return RedirectResponse(url=destino, status_code=302)


@router.get("/bienvenida/{token}/skool")
async def skool(token: str, db: Session = Depends(get_db)):
    alta = _alta(token, db)
    if not alta.accesos_abiertos or not SKOOL_INVITE_URL:
        raise HTTPException(status_code=404, detail="No encontrado")
    if not alta.skool_abierto_en:
        alta.skool_abierto_en = datetime.utcnow()
        db.commit()
    return RedirectResponse(url=SKOOL_INVITE_URL, status_code=302)


@router.get("/bienvenida/{token}/onboarding")
async def onboarding(token: str, db: Session = Depends(get_db)):
    alta = _alta(token, db)
    if not alta.accesos_abiertos or not CALENDLY_ONBOARDING_URL:
        raise HTTPException(status_code=404, detail="No encontrado")
    if not alta.onboarding_agendado_en:
        alta.onboarding_agendado_en = datetime.utcnow()
        db.commit()
    sep = "&" if "?" in CALENDLY_ONBOARDING_URL else "?"
    destino = f"{CALENDLY_ONBOARDING_URL}{sep}name={alta.nombre}&email={alta.email}"
    return RedirectResponse(url=destino, status_code=302)


# ── Contrato ─────────────────────────────────────────────────────────────────

@router.get("/bienvenida/{token}/contrato", response_class=HTMLResponse)
async def contrato(token: str, request: Request, db: Session = Depends(get_db)):
    alta = _alta(token, db)
    firma = alta.firma
    return templates.TemplateResponse("contrato_firma.html", {
        "request": request,
        "alta": alta,
        "firma": firma,
        "d": _documento(alta, firma=firma),
        "reconocimientos": RECONOCIMIENTOS,
    })


@router.post("/bienvenida/{token}/firmar")
async def firmar(
    token: str,
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
    r_compromiso: Optional[str] = Form(None),
    r_arbitraje: Optional[str] = Form(None),
):
    alta = _alta(token, db)
    if alta.firma is not None:
        return RedirectResponse(url=f"/bienvenida/{token}/contrato", status_code=303)

    marcados = [c for c, v in (("resultados", r_resultados), ("devoluciones", r_devoluciones),
                               ("compromiso", r_compromiso), ("arbitraje", r_arbitraje)) if v]

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
        return volver("Tienes que marcar los cuatro reconocimientos para poder firmar.")
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
    return RedirectResponse(url=f"/bienvenida/{token}/contrato", status_code=303)


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

@router.post("/bienvenida/{token}/cuenta")
async def crear_cuenta(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(""),
    password: str = Form(""),
    password2: str = Form(""),
):
    alta = _alta(token, db)

    def volver(error: str):
        return templates.TemplateResponse("bienvenida.html", {
            "request": request, "alta": alta, "pasos": _pasos(alta),
            "abiertos": alta.accesos_abiertos, "error_cuenta": error,
            "email_previo": email,
        }, status_code=400)

    if not alta.accesos_abiertos:
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
