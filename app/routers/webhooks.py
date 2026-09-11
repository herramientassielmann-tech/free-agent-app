"""Avisos de Calendly y Stripe.

Dos rutas públicas más, y las únicas de la app que reciben datos de fuera. Por
eso ambas verifican la firma antes de mirar el contenido: sin eso, cualquiera
que descubra la URL podría darse de alta o marcarse como pagado.

La verificación se hace a mano con hmac en vez de con los SDK de Stripe y
Calendly. Las dos usan el mismo esquema —HMAC-SHA256 sobre "timestamp.cuerpo"—
y son quince líneas; los SDK son dos dependencias más en el servidor para esto.

Todo es idempotente: el mismo aviso repetido no duplica ni vuelve a marcar nada.
Las pasarelas reintentan cuando no reciben un 200, así que llegan repetidos por
diseño, no por avería.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import CALENDLY_WEBHOOK_SECRET, STRIPE_WEBHOOK_SECRET
from app.database import get_db
from app.models import Alta
from app.routers.bienvenida import caducidad, nuevo_token

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks")

# Margen de reloj aceptado. Cinco minutos es lo que recomienda Stripe: suficiente
# para un reintento legítimo, corto para reutilizar un aviso capturado.
TOLERANCIA_SEG = 300


def _firma_valida(cuerpo: bytes, cabecera: str, secreto: str) -> bool:
    """Comprueba la cabecera "t=...,v1=..." que mandan Stripe y Calendly."""
    if not cabecera or not secreto:
        return False
    partes = dict(
        p.split("=", 1) for p in cabecera.split(",") if "=" in p
    )
    t, v1 = partes.get("t"), partes.get("v1")
    if not t or not v1:
        return False
    try:
        # time.time() y no datetime.utcnow().timestamp(): lo segundo interpreta
        # una fecha ingenua como hora LOCAL, así que en España se iría dos horas
        # y rechazaría todas las firmas legítimas.
        if abs(time.time() - int(t)) > TOLERANCIA_SEG:
            return False
    except ValueError:
        return False
    esperada = hmac.new(
        secreto.encode(), f"{t}.".encode() + cuerpo, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(esperada, v1)


# ── Calendly ─────────────────────────────────────────────────────────────────

@router.post("/calendly")
async def calendly(
    request: Request,
    db: Session = Depends(get_db),
    calendly_webhook_signature: Optional[str] = Header(default=None),
):
    cuerpo = await request.body()
    if not _firma_valida(cuerpo, calendly_webhook_signature or "", CALENDLY_WEBHOOK_SECRET or ""):
        raise HTTPException(status_code=401, detail="Firma no válida")

    datos = json.loads(cuerpo or b"{}")
    evento = datos.get("event") or ""
    p = datos.get("payload") or {}
    uri = p.get("uri") or ""
    if not uri:
        return {"ok": True, "ignorado": "sin uri"}

    alta = db.query(Alta).filter(Alta.calendly_uri == uri).first()

    if evento == "invitee.canceled":
        # No se borra: si la persona reagenda queremos el historial, y si ya
        # firmó o pagó el expediente tiene que seguir existiendo.
        if alta and not alta.completada:
            alta.programada_para = None
            db.commit()
        return {"ok": True}

    if evento != "invitee.created":
        return {"ok": True, "ignorado": evento}

    inicio = None
    crudo = ((p.get("scheduled_event") or {}).get("start_time") or "")
    if crudo:
        try:
            inicio = datetime.fromisoformat(crudo.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            inicio = None

    if alta:                       # reagendada: se mueve la hora, nada más
        alta.programada_para = inicio
        if not alta.email_enviado_en:
            alta.nombre = p.get("name") or alta.nombre
            alta.email = (p.get("email") or alta.email).strip().lower()
        db.commit()
        return {"ok": True, "alta": alta.id, "reagendada": True}

    alta = Alta(
        nombre=(p.get("name") or "Sin nombre")[:150],
        email=(p.get("email") or "").strip().lower()[:255],
        telefono=(p.get("text_reminder_number") or None),
        programada_para=inicio,
        calendly_uri=uri[:300],
        token=nuevo_token(),
        token_expira=caducidad(),
    )
    db.add(alta)
    db.commit()
    db.refresh(alta)
    log.info("Alta creada desde Calendly: %s (%s)", alta.nombre, alta.email)
    return {"ok": True, "alta": alta.id}


# ── Stripe ───────────────────────────────────────────────────────────────────

@router.post("/stripe")
async def stripe(
    request: Request,
    db: Session = Depends(get_db),
    stripe_signature: Optional[str] = Header(default=None),
):
    cuerpo = await request.body()
    if not _firma_valida(cuerpo, stripe_signature or "", STRIPE_WEBHOOK_SECRET or ""):
        raise HTTPException(status_code=401, detail="Firma no válida")

    datos = json.loads(cuerpo or b"{}")
    if datos.get("type") != "checkout.session.completed":
        return {"ok": True, "ignorado": datos.get("type")}

    sesion = (datos.get("data") or {}).get("object") or {}
    if sesion.get("payment_status") != "paid":
        return {"ok": True, "ignorado": "sin pagar"}

    # client_reference_id es lo que enlaza el cobro con el alta. Lo pone la URL
    # del enlace de pago que construye /bienvenida/{token}/pagar.
    ref = sesion.get("client_reference_id") or ""
    alta = None
    if ref.startswith("alta_"):
        try:
            alta = db.get(Alta, int(ref[5:]))
        except ValueError:
            alta = None
    if alta is None:
        # Respaldo por correo: si alguien paga desde un enlace suelto sin la
        # referencia, al menos no se pierde el cobro.
        correo = ((sesion.get("customer_details") or {}).get("email") or "").strip().lower()
        if correo:
            alta = db.query(Alta).filter(Alta.email == correo).order_by(Alta.id.desc()).first()
    if alta is None:
        log.warning("Pago de Stripe sin alta que lo reclame: %s", sesion.get("id"))
        return {"ok": True, "ignorado": "sin alta"}

    if alta.pagado_en:
        return {"ok": True, "alta": alta.id, "repetido": True}

    metodos = sesion.get("payment_method_types") or []
    alta.pagado_en = datetime.utcnow()
    alta.metodo_pago = "ach" if "us_bank_account" in metodos else "tarjeta"
    alta.stripe_session = (sesion.get("id") or "")[:200]
    db.commit()
    log.info("Pago confirmado para el alta %s (%s)", alta.id, alta.metodo_pago)
    return {"ok": True, "alta": alta.id}
