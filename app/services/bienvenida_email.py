"""Los correos del alta: la bienvenida y los recordatorios.

Viven aquí y no dentro del script programado porque el panel de admin también
los manda (el botón de reenviar), y duplicar el texto de un correo es la forma
más segura de que acaben diciendo cosas distintas.

Un correo por persona con lo que le falta, nunca uno por cada cosa pendiente.
"""
from datetime import datetime
from typing import List, Optional

from app.config import APP_URL
from app.models import Alta

# Qué le falta, en el orden en que tiene que hacerlo.
PENDIENTES = [
    ("pagado_en", "Completar el pago"),
    ("contrato_firmado_en", "Firmar el contrato"),
    ("cuenta_creada_en", "Crear tu cuenta en la herramienta"),
    ("skool_abierto_en", "Entrar en Skool"),
    ("onboarding_agendado_en", "Agendar tu llamada de onboarding"),
]


def que_falta(alta: Alta) -> List[str]:
    return [texto for campo, texto in PENDIENTES if not getattr(alta, campo, None)]


def _enviar(destinatario: str, asunto: str, html: str, texto: str) -> bool:
    try:
        from app.services.email import enviar, esta_configurado
        if not esta_configurado():
            return False
        return enviar(destinatario, asunto, html, texto)
    except Exception:
        return False


def _plantilla(titulo: str, parrafos: List[str], enlace: str,
               boton: str, faltan: Optional[List[str]] = None) -> str:
    cuerpo = "".join(f'<p style="margin:0 0 14px">{p}</p>' for p in parrafos)
    lista = ""
    if faltan:
        filas = "".join(
            f'<tr><td style="padding:7px 0;border-bottom:1px solid #E4E9EF;font-size:15px">'
            f'{i}. {f}</td></tr>' for i, f in enumerate(faltan, 1)
        )
        lista = f'<table role="presentation" width="100%" style="margin:4px 0 20px">{filas}</table>'
    return f'''<!doctype html><html lang="es"><body style="margin:0;background:#F1F4F8;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:#F1F4F8;padding:32px 16px"><tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="max-width:520px;background:#FFF;border-radius:12px;
                  border:1px solid #E4E9EF;padding:30px"><tr><td>
      <p style="margin:0 0 6px;font-size:12px;color:#5A6874;text-transform:uppercase;
                letter-spacing:.6px">Free Agent Academy</p>
      <h1 style="margin:0 0 16px;font-size:21px;color:#16202C;font-weight:600;
                 line-height:1.3">{titulo}</h1>
      <div style="font-size:15px;color:#16202C;line-height:1.6">{cuerpo}</div>
      {lista}
      <p style="margin:6px 0 0">
        <a href="{enlace}" style="display:inline-block;background:#0A6FD4;color:#FFF;
           text-decoration:none;padding:12px 24px;border-radius:9px;font-size:15px;
           font-weight:600">{boton}</a>
      </p>
    </td></tr></table>
    <p style="max-width:520px;margin:16px auto 0;font-size:12px;color:#5A6874">
      Este enlace es sólo tuyo. Si no lo esperabas, ignora este correo.
    </p>
  </td></tr></table></body></html>'''


def mandar_bienvenida(alta: Alta) -> bool:
    """Sale a la hora exacta de la llamada de venta, para que el cierre se pueda
    hacer en vivo mientras la persona está al teléfono."""
    enlace = f"{APP_URL}/bienvenida/{alta.token}"
    nombre = (alta.nombre or "").split()[0] or "Hola"
    faltan = que_falta(alta)
    return _enviar(
        alta.email,
        "Tu acceso a Free Agent Academy",
        _plantilla(
            f"{nombre}, aquí tienes todo",
            ["Este es tu enlace personal. Desde ahí haces el pago, firmas el "
             "contrato, creas tu cuenta en la herramienta, entras en Skool y "
             "agendas tu llamada de onboarding.",
             "Lo puedes hacer ahora mismo durante la llamada. Si te quedas a "
             "medias, vuelves al mismo enlace cuando quieras."],
            enlace, "Abrir mi acceso", faltan),
        f"{nombre}, aquí tienes tu acceso a Free Agent Academy:\n{enlace}\n\n"
        + "\n".join(f"{i}. {f}" for i, f in enumerate(faltan, 1)) + "\n",
    )


def mandar_recordatorio(alta: Alta, dia: int) -> bool:
    """Días 1, 3 y 7. Sólo con lo que le falte: repetirle lo que ya hizo es la
    forma más rápida de que deje de abrir los correos."""
    faltan = que_falta(alta)
    if not faltan:
        return False
    enlace = f"{APP_URL}/bienvenida/{alta.token}"
    nombre = (alta.nombre or "").split()[0] or "Hola"
    uno = len(faltan) == 1

    if dia == 1:
        titulo = f"{nombre}, te queda {'una cosa' if uno else 'poco'}"
        parrafos = ["Ayer empezaste tu alta y quedó a medias. Son dos minutos."]
    elif dia == 3:
        titulo = f"{nombre}, ¿te ayudamos con algo?"
        parrafos = ["Sigue pendiente esto de tu alta. Si algo no te funciona o "
                    "tienes una duda, respóndenos a este correo y lo vemos."]
    else:
        titulo = f"{nombre}, tu enlace caduca pronto"
        parrafos = ["Tu alta sigue sin completar y el enlace tiene fecha de "
                    "caducidad. Si ya no te interesa, dínoslo sin problema; y si "
                    "es que se te ha pasado, aquí lo tienes."]

    return _enviar(
        alta.email, titulo,
        _plantilla(titulo, parrafos, enlace, "Terminar mi alta", faltan),
        f"{titulo}\n\n" + "\n".join(f"- {f}" for f in faltan) + f"\n\n{enlace}\n",
    )
