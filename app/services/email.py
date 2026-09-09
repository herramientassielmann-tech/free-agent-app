"""Envío de correo transaccional a través de Resend.

Se llama a la API con httpx en lugar de usar el SDK de Resend: es una única
petición POST y no justifica otra dependencia en el servidor.

Por qué Resend y no el propio servidor: mandar directamente desde la IP de
Hetzner es garantía de acabar en spam. Las IPs de centro de datos arrastran
mala reputación y el dominio necesita SPF y DKIM firmados por quien envía.

Ninguna función de aquí lanza excepciones hacia arriba. Un aviso que no sale
no puede tumbar el proceso que lo manda: se registra y se reintenta al día
siguiente, que para un recordatorio de tareas es suficiente.
"""
import logging
from typing import Optional

import httpx

from app.config import RESEND_API_KEY, EMAIL_FROM, EMAIL_REPLY_TO

log = logging.getLogger(__name__)

API = "https://api.resend.com/emails"


def esta_configurado() -> bool:
    """False mientras no haya clave. El resto de la app funciona igual."""
    return bool(RESEND_API_KEY)


def enviar(destinatario: str, asunto: str, html: str,
           texto: Optional[str] = None) -> bool:
    """Manda un correo. Devuelve True solo si Resend lo aceptó.

    El valor de retorno importa: quien llama no debe dar por avisado a nadie
    si esto devuelve False, o el aviso se perdería para siempre.
    """
    if not esta_configurado():
        log.warning("RESEND_API_KEY no configurada: no se envía nada a %s", destinatario)
        return False

    cuerpo = {
        "from": EMAIL_FROM,
        "to": [destinatario],
        "subject": asunto,
        "html": html,
    }
    if texto:
        cuerpo["text"] = texto
    if EMAIL_REPLY_TO:
        cuerpo["reply_to"] = EMAIL_REPLY_TO

    try:
        r = httpx.post(
            API,
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json=cuerpo,
            timeout=20,
        )
    except Exception as e:
        log.error("Fallo de red enviando a %s: %s", destinatario, e)
        return False

    if r.status_code >= 300:
        # El cuerpo de Resend dice el motivo (dominio sin verificar, etc.).
        log.error("Resend rechazó el envío a %s (%s): %s",
                  destinatario, r.status_code, r.text[:300])
        return False

    return True
