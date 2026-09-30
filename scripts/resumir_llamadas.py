"""Trae de Fireflies las llamadas nuevas y guarda un resumen de cada una.

Lo lanza un temporizador de systemd dos veces al día, a las 13:00 y a las
20:00. Qué hace:

  1. Pregunta a Fireflies por las últimas llamadas.
  2. Se queda con las que no tenemos ya guardadas.
  3. Baja la transcripción de cada una y le pide a Claude el resumen, los
     acuerdos y lo que necesita atención.
  4. Lo guarda. La transcripción entera NO se guarda: ya vive en Fireflies y
     ocupa; aquí queda lo que de verdad se consulta después.

Decisiones que conviene entender antes de tocar nada:

  · **Una llamada se resume una sola vez.** `fireflies_id` es único y se
    comprueba antes de bajar nada. El trabajo corre dos veces al día: sin esto
    se pagaría dos veces por el mismo resumen.
  · **Si una llamada falla, las demás siguen.** Una transcripción rara o una
    llamada de un minuto no puede dejar sin resumir a las otras cinco.
  · **Las llamadas de menos de 3 minutos se saltan.** Son reuniones que se
    cayeron o pruebas; resumirlas es gastar por nada.

Uso:
    .venv/bin/python3 scripts/resumir_llamadas.py            # normal
    .venv/bin/python3 scripts/resumir_llamadas.py --ensayo   # sin guardar
    .venv/bin/python3 scripts/resumir_llamadas.py --dias 7   # mirar más atrás
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import anthropic

from app.config import ANTHROPIC_API_KEY, FIREFLIES_API_KEY
from app.database import SessionLocal
from app.models import LlamadaResumen

API = "https://api.fireflies.ai/graphql"

# Menos de esto es una reunión que no llegó a empezar.
MINIMO_MINUTOS = 3

INSTRUCCIONES = """Eres quien lleva el seguimiento de una academia que enseña a agentes
inmobiliarios a hacer contenido en vídeo. Acabas de leer la transcripción de una llamada.

Devuelve SOLO un objeto JSON con estas tres claves, en español:

  "resumen":  3-5 frases. Qué se enseñó o se decidió. Concreto, sin relleno.
  "acuerdos": lista de strings. Lo que alguien se ha comprometido a hacer, con
              el nombre delante. Lista vacía si no se acordó nada.
  "atencion": lista de strings. Lo que conviene que el equipo sepa: alguien
              atascado, una objeción, una duda que se repite, una oportunidad
              que nadie recogió. Lista vacía si no hay nada.

No inventes nada que no esté en la transcripción. Si algo no queda claro, omítelo."""


def _pedir(consulta: str, variables: dict) -> dict:
    """Una llamada a la API de Fireflies. Devuelve `data` o lanza."""
    cuerpo = json.dumps({"query": consulta, "variables": variables}).encode()
    req = urllib.request.Request(API, data=cuerpo, headers={
        "Authorization": f"Bearer {FIREFLIES_API_KEY}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        datos = json.loads(r.read().decode())
    if datos.get("errors"):
        raise RuntimeError(json.dumps(datos["errors"])[:300])
    return datos["data"]


def _resumir(titulo: str, texto: str) -> dict:
    """Le pide a Claude el resumen. Lanza con el motivo si no se pudo.

    `max_tokens` holgado a propósito: con 1.200 las llamadas largas se quedaban
    con el JSON cortado a media frase y fallaban todas al interpretarlo. Se
    pagan los tokens que se usan, no el tope, así que poner margen no cuesta.
    """
    cliente = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = cliente.messages.create(
        model="claude-sonnet-5",
        max_tokens=4000,
        system=INSTRUCCIONES,
        messages=[{"role": "user",
                   "content": f"Llamada: «{titulo}»\n\nTranscripción:\n\n{texto[:120000]}"}],
    )
    if msg.stop_reason == "max_tokens":
        raise RuntimeError("el resumen se cortó por el tope de tokens")

    bloque = next((b for b in msg.content if b.type == "text"), None)
    if not bloque:
        raise RuntimeError("el modelo no devolvió texto")

    bruto = bloque.text.strip()
    # A veces lo envuelve en un bloque de código.
    if bruto.startswith("```"):
        bruto = bruto.split("```")[1]
        bruto = bruto[4:] if bruto.startswith("json") else bruto
    bruto = bruto.strip()
    try:
        d = json.loads(bruto)
    except ValueError as e:
        raise RuntimeError(f"no devolvió JSON válido ({e}); empieza por: {bruto[:80]!r}")
    if not isinstance(d, dict):
        raise RuntimeError("el JSON no era un objeto")
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensayo", action="store_true", help="enseña lo que haría, sin guardar")
    ap.add_argument("--dias", type=int, default=3, help="cuántos días atrás mirar")
    args = ap.parse_args()

    if not FIREFLIES_API_KEY:
        print("Falta FIREFLIES_API_KEY en el .env. No hago nada.")
        return 1

    desde = datetime.utcnow() - timedelta(days=args.dias)
    db = SessionLocal()
    try:
        try:
            datos = _pedir(
                "query { transcripts(limit: 25) { id title date duration participants } }", {})
        except Exception as e:                       # noqa: BLE001
            print(f"No se pudo hablar con Fireflies: {e}")
            return 1

        ya = {x[0] for x in db.query(LlamadaResumen.fireflies_id).all()}
        nuevas, saltadas, fallos = 0, 0, 0

        for t in datos.get("transcripts") or []:
            fid = t.get("id") or ""
            # `utcfromtimestamp` está en retirada y avisaba en cada pasada, dos
            # veces al día. Se construye con zona y se guarda sin ella, que es
            # como almacena las fechas el resto de la app.
            cuando = datetime.fromtimestamp((t.get("date") or 0) / 1000,
                                            timezone.utc).replace(tzinfo=None)
            minutos = round(t.get("duration") or 0)

            if fid in ya or cuando < desde:
                continue
            if minutos < MINIMO_MINUTOS:
                print(f"  — «{t.get('title')}» ({minutos} min): demasiado corta, la salto")
                saltadas += 1
                continue

            print(f"  · {cuando:%d/%m %H:%M} «{t.get('title')}» ({minutos} min)…")
            try:
                detalle = _pedir(
                    "query($id: String!) { transcript(id: $id) { sentences { speaker_name text } } }",
                    {"id": fid})
                frases = (detalle.get("transcript") or {}).get("sentences") or []
                texto = "\n".join(f"{f.get('speaker_name')}: {f.get('text')}" for f in frases)
                if not texto.strip():
                    print("      sin transcripción, la salto")
                    saltadas += 1
                    continue

                r = _resumir(t.get("title") or "Llamada", texto)

                fila = LlamadaResumen(
                    fireflies_id=fid,
                    titulo=(t.get("title") or "Llamada")[:300],
                    fecha=cuando,
                    duracion_min=minutos,
                    participantes=", ".join(t.get("participants") or [])[:400] or None,
                    resumen=r.get("resumen") or None,
                    acuerdos="\n".join(r.get("acuerdos") or []) or None,
                    atencion="\n".join(r.get("atencion") or []) or None,
                )
                if not args.ensayo:
                    db.add(fila)
                    db.commit()
                nuevas += 1
                print(f"      ✅ {(r.get('resumen') or '')[:90]}…")
            except Exception as e:                   # noqa: BLE001
                # Una llamada rara no puede dejar sin resumir a las demás.
                db.rollback()
                fallos += 1
                print(f"      ❌ {str(e)[:120]}")

        print()
        print(f"Resumidas: {nuevas} | Saltadas: {saltadas} | Fallidas: {fallos}")
        if args.ensayo:
            print("(ensayo: no se ha guardado nada)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
