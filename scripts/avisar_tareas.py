"""Avisa por email de las tareas del CRM que llegan a su fecha sin marcar.

Lo lanza un temporizador de systemd una vez al día. Qué hace:

  1. Busca tareas pendientes cuya fecha límite ya llegó (hoy o antes) y de las
     que todavía no se ha avisado.
  2. Agrupa por realtor y manda UN correo a cada uno con todas las suyas.
  3. Marca las tareas como avisadas, pero solo si el correo salió de verdad.

Tres decisiones que conviene entender antes de tocar nada:

  · Un correo por persona, no por tarea. Cinco correos un lunes por la mañana
    no se leen: se archivan en bloque y el siguiente ya no se abre.

  · Cada tarea avisa una sola vez. No se insiste al día siguiente ni al otro.
    El recordatorio de que algo sigue pendiente ya está en el tablero, en rojo,
    donde no molesta. Un correo diario repitiendo lo mismo acaba en spam por
    la vía más cara: la de que el realtor lo marque como tal.

  · `avisada_en` se escribe solo si Resend aceptó el envío. Si falla la red o
    el dominio no está verificado, la tarea queda sin avisar y mañana se
    reintenta. Marcarla antes de enviar perdería el aviso para siempre.

Uso:
    .venv/bin/python3 scripts/avisar_tareas.py            # envía de verdad
    .venv/bin/python3 scripts/avisar_tareas.py --ensayo   # enseña qué mandaría
    .venv/bin/python3 scripts/avisar_tareas.py --prueba tu@correo.com
"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import APP_URL, EMAIL_FROM
from app.database import SessionLocal
from app.models import Lead, LeadTarea, User
from app.services.email import enviar, esta_configurado


# ── Redacción del correo ───────────────────────────────────────────────────

def _dias(fecha: datetime, hoy) -> str:
    d = (hoy - fecha.date()).days
    if d <= 0:
        return "hoy"
    if d == 1:
        return "ayer"
    return f"hace {d} días"


def _asunto(tareas) -> str:
    if len(tareas) == 1:
        return f"Tienes una tarea pendiente: {tareas[0].texto[:60]}"
    return f"Tienes {len(tareas)} tareas pendientes en tu CRM"


def _html(nombre: str, tareas, hoy) -> str:
    filas = "".join(
        f'''<tr>
              <td style="padding:10px 0;border-bottom:1px solid #E4E9EF">
                <div style="font-size:15px;color:#16202C">{_escapar(t.texto)}</div>
                <div style="font-size:13px;color:#5A6874;margin-top:2px">
                  {_escapar(t.lead.nombre)} · vencía {_dias(t.fecha_limite, hoy)}
                </div>
              </td>
            </tr>'''
        for t in tareas
    )
    plural = "estas tareas" if len(tareas) > 1 else "esta tarea"
    return f'''<!doctype html>
<html lang="es"><body style="margin:0;background:#F1F4F8;
  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:#F1F4F8;padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:520px;background:#FFFFFF;border-radius:12px;
                    border:1px solid #E4E9EF;padding:28px">
        <tr><td>
          <p style="margin:0 0 4px;font-size:13px;color:#5A6874;
                    text-transform:uppercase;letter-spacing:.5px">Free Agent Academy</p>
          <h1 style="margin:0 0 16px;font-size:20px;color:#16202C;font-weight:600">
            {_escapar(nombre)}, se te ha pasado la fecha de {plural}
          </h1>
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            {filas}
          </table>
          <p style="margin:22px 0 0">
            <a href="{APP_URL}/crm/tareas"
               style="display:inline-block;background:#16202C;color:#FFFFFF;
                      text-decoration:none;padding:11px 20px;border-radius:8px;
                      font-size:15px;font-weight:500">Ver mis tareas</a>
          </p>
          <p style="margin:22px 0 0;font-size:13px;color:#5A6874;line-height:1.5">
            La mayoría de operaciones se cierran meses después del primer mensaje,
            con quien sigue ahí. Un mensaje de dos líneas cuenta.
          </p>
        </td></tr>
      </table>
      <p style="max-width:520px;margin:16px auto 0;font-size:12px;color:#5A6874">
        Recibes esto porque tienes tareas con fecha en tu CRM.
        Cada tarea avisa una sola vez.
      </p>
    </td></tr>
  </table>
</body></html>'''


def _texto(nombre: str, tareas, hoy) -> str:
    lineas = [f"- {t.texto} ({t.lead.nombre}, vencía {_dias(t.fecha_limite, hoy)})"
              for t in tareas]
    return (f"{nombre}, tienes tareas pendientes en tu CRM:\n\n"
            + "\n".join(lineas)
            + f"\n\nVerlas: {APP_URL}/crm/tareas\n")


def _escapar(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


# ── Proceso ────────────────────────────────────────────────────────────────

def avisar(ensayo: bool = False) -> int:
    hoy = datetime.utcnow().date()
    db = SessionLocal()
    try:
        pendientes = (
            db.query(LeadTarea)
            .join(Lead, LeadTarea.lead_id == Lead.id)
            .filter(
                LeadTarea.hecha.is_(False),
                LeadTarea.avisada_en.is_(None),
                LeadTarea.fecha_limite.isnot(None),
                LeadTarea.fecha_limite < datetime.combine(hoy, datetime.max.time()),
            )
            .order_by(LeadTarea.fecha_limite)
            .all()
        )

        # Agrupadas por realtor: un correo cada uno, no uno por tarea.
        # Se descartan aquí las de cuentas dadas de baja, para que no cuenten
        # como envíos fallidos al final.
        por_realtor = {}
        for t in pendientes:
            user = db.get(User, t.lead.user_id)
            if not user or not user.is_active or not user.email:
                continue
            por_realtor.setdefault(user, []).append(t)

        if not por_realtor:
            print(f"[{hoy}] Nada que avisar.")
            return 0

        enviados = 0
        for user, tareas in por_realtor.items():
            nombre = (user.name or "").split()[0] or "Hola"
            asunto = _asunto(tareas)

            if ensayo:
                print(f"\n── {user.email} ── «{asunto}»")
                for t in tareas:
                    print(f"   · {t.texto}  [{t.lead.nombre}, "
                          f"vencía {_dias(t.fecha_limite, hoy)}]")
                continue

            ok = enviar(user.email, asunto,
                        _html(nombre, tareas, hoy),
                        _texto(nombre, tareas, hoy))
            if ok:
                # Solo ahora: si el envío falló, mañana se reintenta.
                for t in tareas:
                    t.avisada_en = datetime.utcnow()
                db.commit()
                enviados += 1
                print(f"[{hoy}] Avisado {user.email} · {len(tareas)} tarea(s)")
            else:
                db.rollback()
                print(f"[{hoy}] FALLO al avisar a {user.email} — se reintenta mañana")

        if ensayo:
            total = sum(len(v) for v in por_realtor.values())
            print(f"\n(ensayo) {len(por_realtor)} realtor(s), "
                  f"{total} tarea(s). No se ha enviado ni marcado nada.")
            return 0

        # Código 1 si alguien se quedó sin aviso, para que systemd lo registre.
        return 0 if enviados == len(por_realtor) else 1
    finally:
        db.close()


def prueba(destino: str) -> int:
    """Manda un correo de muestra. Sirve para validar el DNS sin esperar
    a que venza una tarea de verdad."""
    class _L:  nombre = "Lead de prueba"
    class _T:
        texto = "Llamar para confirmar la visita del jueves"
        fecha_limite = datetime.utcnow()
        lead = _L()

    hoy = datetime.utcnow().date()
    print(f"Enviando desde {EMAIL_FROM} a {destino}…")
    ok = enviar(destino, "Prueba de avisos — Free Agent Academy",
                _html("Robert", [_T()], hoy), _texto("Robert", [_T()], hoy))
    print("Enviado. Míralo en la bandeja (y en spam)." if ok
          else "No se pudo enviar. Revisa RESEND_API_KEY y el dominio verificado.")
    return 0 if ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--prueba" in args:
        i = args.index("--prueba")
        if i + 1 >= len(args):
            print("Falta el correo: --prueba tu@correo.com")
            sys.exit(2)
        sys.exit(prueba(args[i + 1]))

    ensayo = "--ensayo" in args
    if not ensayo and not esta_configurado():
        print("RESEND_API_KEY no configurada. Nada que hacer.")
        sys.exit(0)
    sys.exit(avisar(ensayo=ensayo))
