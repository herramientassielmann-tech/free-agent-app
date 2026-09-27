"""Enlaces de seguimiento: /r/<codigo>

Un enlace por sitio donde se publica. Quien lo pulsa queda registrado y sale
hacia la landing con los parámetros UTM puestos, que es lo que permite saber
después de dónde vino cada reunión agendada.

Por qué pasa por aquí y no se enlaza la landing directamente: la landing está en
otro alojamiento y no tiene analítica ninguna, así que sin este salto no hay
forma de contar nada. El salto añade unos milisegundos y nos da el dato.

Regla de oro de este módulo: **el visitante nunca paga nuestros fallos**. Si la
base de datos no responde, se le redirige igual. Un clic sin registrar es un
dato perdido; un visitante con un error en pantalla es un cliente perdido.
"""
import hashlib
import logging
import re
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import LANDING_URL, SECRET_KEY
from app.database import get_db
from app.models import ClicEnlace

log = logging.getLogger(__name__)

router = APIRouter()

# Letras, números, guiones y guiones bajos. Lo que no encaje se ignora: el
# código acaba en una URL pública y no queremos que entre cualquier cosa.
CODIGO_OK = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _ip(request: Request) -> str:
    """La IP real del visitante, que detrás de nginx no es la de la conexión."""
    reenviada = request.headers.get("x-forwarded-for") or ""
    if reenviada:
        return reenviada.split(",")[0].strip()
    return request.client.host if request.client else ""


def _visitante(request: Request, codigo: str) -> str:
    """Un identificador para contar personas distintas SIN guardar quién es.

    Es un hash de IP + navegador + código, con la clave del servidor de sal. No
    se puede volver atrás para sacar la IP, y sirve para no contar cinco veces a
    quien abre el enlace cinco veces.
    """
    crudo = f"{_ip(request)}|{request.headers.get('user-agent', '')}|{codigo}|{SECRET_KEY}"
    return hashlib.sha256(crudo.encode()).hexdigest()[:48]


# ── Aviso desde la landing ───────────────────────────────────────────────────

# Solo estos. No se acepta cualquier etiqueta: el endpoint es público y sin
# lista blanca acabaría lleno de lo que le mande cualquiera.
TIPOS_OK = {"formulario"}


@router.api_route("/r/evento", methods=["GET", "POST"])
async def evento(
    request: Request,
    codigo: str = "",
    tipo: str = "formulario",
    db: Session = Depends(get_db),
):
    """La landing avisa de que alguien ha enviado el Typeform.

    Se llama con `navigator.sendBeacon`, que dispara y se olvida: la respuesta
    no la mira nadie y no puede frenar el formulario. Por eso este endpoint
    devuelve siempre 204 pase lo que pase — si algo falla aquí, el problema es
    nuestro y no del visitante que está intentando reservar.
    """
    respuesta = Response(status_code=204)
    # La landing vive en otro dominio: sin esto el navegador descarta la llamada.
    respuesta.headers["Access-Control-Allow-Origin"] = "*"

    if tipo not in TIPOS_OK or not CODIGO_OK.match(codigo or ""):
        return respuesta
    try:
        db.add(ClicEnlace(
            codigo=codigo,
            tipo=tipo,
            referente=(request.headers.get("referer") or None),
            agente=(request.headers.get("user-agent") or None),
            visitante=_visitante(request, codigo),
        ))
        db.commit()
    except Exception as e:                           # noqa: BLE001
        db.rollback()
        log.warning("No se pudo registrar el evento %s de %s: %s", tipo, codigo, e)
    return respuesta


# Esta ruta va ANTES que /r/{codigo} a propósito: FastAPI resuelve por orden
# de declaración y el comodín se tragaría «evento».
@router.get("/r/{codigo}")
async def seguir(codigo: str, request: Request, db: Session = Depends(get_db)):
    """Registra la visita y manda a la landing con los UTM puestos."""
    valido = bool(CODIGO_OK.match(codigo))

    if valido:
        try:
            db.add(ClicEnlace(
                codigo=codigo,
                tipo="visita",
                referente=(request.headers.get("referer") or None),
                agente=(request.headers.get("user-agent") or None),
                visitante=_visitante(request, codigo),
            ))
            db.commit()
        except Exception as e:                       # noqa: BLE001
            # Nunca se le enseña un error a quien venía a ver la web.
            db.rollback()
            log.warning("No se pudo registrar el clic de %s: %s", codigo, e)

    destino = LANDING_URL.rstrip("/")
    if valido:
        # Estos tres son los que el widget de Calendly arrastra hasta la reserva.
        destino += "/?" + urlencode({
            "utm_source": codigo,
            "utm_medium": "enlace",
            "utm_campaign": codigo,
        })

    # 302 y no 301: un 301 se queda cacheado en el navegador para siempre y a
    # partir del segundo clic dejaríamos de contar.
    return RedirectResponse(url=destino, status_code=302)
