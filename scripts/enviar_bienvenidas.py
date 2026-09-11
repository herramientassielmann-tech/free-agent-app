"""Manda el correo de bienvenida a la hora de la llamada, y los recordatorios.

Corre cada cinco minutos. Hace dos cosas:

  1. **La bienvenida.** Sale a la hora EXACTA de la llamada de venta, no antes.
     Es lo que permite cerrar en vivo: mientras Robert habla con la persona, a
     esa persona le llega el enlace con el pago, el contrato y los accesos. Si
     llegara antes, se abriría solo y frío; si llegara después, el sí ya se
     habría enfriado.

  2. **Los recordatorios de los días 1, 3 y 7**, sólo con lo que le falte. La
     cadencia no es inventada: es la que usan los programas de alto ticket, y
     responde a que la primera semana es donde se pierde a casi todo el que se
     pierde.

Cada correo se da por enviado SÓLO si el proveedor lo aceptó. Marcarlo antes
perdería el aviso para siempre si fallara la red.

Uso:
    .venv/bin/python3 scripts/enviar_bienvenidas.py
    .venv/bin/python3 scripts/enviar_bienvenidas.py --ensayo   # enseña qué haría
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import Alta
from app.services.bienvenida_email import (
    mandar_bienvenida, mandar_recordatorio, que_falta,
)

# Día del recordatorio → número de orden. Se guarda el orden y no la fecha para
# que, si el servidor estuvo caído, se mande el que toque y no los tres de golpe.
CADENCIA = [(1, 1), (3, 2), (7, 3)]
DIAS_PARA_AVISAR = 3   # a partir de aquí se avisa al admin


def _avisar_admin(atascados: list) -> None:
    """Un correo al equipo con quién se ha quedado a medias. Nunca tumba el
    proceso si falla."""
    if not atascados:
        return
    try:
        from app.config import ADMIN_EMAIL, APP_URL
        from app.services.email import enviar, esta_configurado
        if not esta_configurado():
            return
        filas = "".join(
            f"<p style='margin:0 0 8px'><b>{a.nombre}</b> ({a.email}) · "
            f"{dias} días · le falta: {', '.join(que_falta(a)).lower()}</p>"
            for a, dias in atascados
        )
        enviar(
            ADMIN_EMAIL,
            f"{len(atascados)} alta(s) sin terminar",
            f"<div style=\"font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;"
            f"font-size:15px;color:#16202C;line-height:1.5\">{filas}"
            f"<p style='margin-top:14px'><a href='{APP_URL}/admin/altas'>Ver el panel de altas</a></p></div>",
            "\n".join(f"{a.nombre} ({a.email}) · {d} días" for a, d in atascados),
        )
    except Exception as e:
        print(f"  (no se pudo avisar al admin: {e})")


def procesar(ensayo: bool = False) -> int:
    ahora = datetime.utcnow()
    db = SessionLocal()
    fallos = 0
    try:
        # ── 1. Bienvenidas ──
        pendientes = (
            db.query(Alta)
            .filter(Alta.email_enviado_en.is_(None),
                    Alta.programada_para.isnot(None),
                    Alta.programada_para <= ahora)
            .order_by(Alta.programada_para)
            .all()
        )
        for a in pendientes:
            if ensayo:
                print(f"  [bienvenida] {a.email} · llamada {a.programada_para:%d/%m %H:%M}")
                continue
            if mandar_bienvenida(a):
                a.email_enviado_en = ahora
                db.commit()
                print(f"  Bienvenida a {a.email}")
            else:
                db.rollback()
                fallos += 1
                print(f"  FALLO al mandar la bienvenida a {a.email} — se reintenta")

        # ── 2. Recordatorios ──
        abiertas = (
            db.query(Alta)
            .filter(Alta.email_enviado_en.isnot(None))
            .order_by(Alta.email_enviado_en)
            .all()
        )
        atascados = []
        for a in abiertas:
            if a.completada or a.token_expira < ahora:
                continue
            dias = (ahora - a.email_enviado_en).days
            # El que corresponde a HOY, no el primero que quedó pendiente. Si
            # el servidor estuvo caído tres días, mandar el de "ayer empezaste"
            # el cuarto día suena a robot; se salta al que toca y se pone el
            # contador al día, sin mandar los tres de golpe.
            alcanzados = [(d, orden) for d, orden in CADENCIA if dias >= d]
            if not alcanzados:
                continue
            dia, toca = alcanzados[-1]
            if a.recordatorios_enviados >= toca:
                continue
            if dias >= DIAS_PARA_AVISAR:
                atascados.append((a, dias))
            if ensayo:
                print(f"  [recordatorio día {dia}] {a.email} · le falta: "
                      f"{', '.join(que_falta(a)).lower()}")
                continue
            if mandar_recordatorio(a, dia):
                a.recordatorios_enviados = toca
                db.commit()
                print(f"  Recordatorio día {dia} a {a.email}")
            else:
                db.rollback()
                fallos += 1
                print(f"  FALLO al recordar a {a.email} — se reintenta")

        if ensayo:
            total = len(pendientes) + len(atascados)
            print(f"\n(ensayo) {total} correo(s) saldrían. No se ha mandado ni marcado nada.")
            return 0

        _avisar_admin(atascados)
        if not pendientes and not atascados:
            print(f"[{ahora:%d/%m %H:%M}] Nada que mandar.")
        return 1 if fallos else 0
    finally:
        db.close()


if __name__ == "__main__":
    ensayo = "--ensayo" in sys.argv[1:]
    if not ensayo:
        from app.services.email import esta_configurado
        if not esta_configurado():
            print("RESEND_API_KEY no configurada. Nada que hacer.")
            sys.exit(0)
    sys.exit(procesar(ensayo=ensayo))
