"""Devuelve el caption a las copias personales que lo perdieron.

Contexto. La vista de una idea inicial construía sus secciones sin incluir
`caption`, así que la tarjeta salía vacía en las 23 aunque el texto estuviera
guardado en la columna todo el tiempo. Eso ya está arreglado en
`app/routers/ideas.py`.

Queda un resto. Mientras duró el fallo, quien editara una idea guardaba su
copia personal con `caption: ""` —el editor leía la tarjeta vacía y la
guardaba tal cual—. Y una copia personal manda sobre el original:

    _secciones()  ->  edicion.get("caption", original["caption"]) or ""

Con la clave presente y vacía, el original no se recupera nunca. Esas copias
seguirían enseñando el caption en blanco después del arreglo.

Qué hace: quita la clave `caption` SOLO cuando está vacía, para que vuelva a
caer sobre el original. No toca el hook, el desarrollo ni la conclusión, que sí
son trabajo del realtor. Un caption con texto se respeta: puede ser suyo.

Se puede relanzar las veces que haga falta.

Uso:
    .venv/bin/python3 scripts/reparar_captions_ideas.py --ensayo   # solo mirar
    .venv/bin/python3 scripts/reparar_captions_ideas.py            # aplicar
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import StarterScript, StarterScriptEdit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ensayo", action="store_true",
                    help="enseña lo que haría sin tocar la base de datos")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        # Primero lo importante: que el original tenga de dónde recuperarse.
        sin_fuente = (
            db.query(StarterScript)
            .filter((StarterScript.caption.is_(None)) | (StarterScript.caption == ""))
            .all()
        )
        if sin_fuente:
            print("⚠️  Estas ideas no tienen caption ni en la columna original,")
            print("    así que no hay nada que recuperar para ellas:")
            for s in sin_fuente:
                print(f"      · idea {s.position} — {s.titulo or s.source_url}")
            print()

        filas = db.query(StarterScriptEdit).all()
        limpiadas, intactas, ilegibles = 0, 0, 0

        for fila in filas:
            try:
                d = json.loads(fila.edicion)
            except (ValueError, TypeError):
                ilegibles += 1
                print(f"  edit {fila.id}: JSON ilegible, no lo toco")
                continue
            if not isinstance(d, dict):
                ilegibles += 1
                continue

            # Solo el caso que causó el fallo: la clave está y está vacía.
            if "caption" in d and not str(d["caption"]).strip():
                original = db.get(StarterScript, fila.starter_script_id)
                recupera = (original.caption or "").strip() if original else ""
                del d["caption"]
                if not args.ensayo:
                    fila.edicion = json.dumps(d, ensure_ascii=False)
                limpiadas += 1
                print(f"  edit {fila.id} (usuario {fila.user_id}, idea "
                      f"{original.position if original else '?'}): caption vacío quitado "
                      f"→ recupera {len(recupera)} caracteres")
            else:
                intactas += 1

        if not args.ensayo:
            db.commit()

        print()
        print("═══════════ RESUMEN ═══════════")
        print(f"Copias personales revisadas : {len(filas)}")
        print(f"  reparadas                 : {limpiadas}")
        print(f"  ya estaban bien           : {intactas}")
        print(f"  ilegibles                 : {ilegibles}")
        print(f"Ideas sin caption de origen : {len(sin_fuente)}")
        if args.ensayo:
            print("\n(ensayo: no se ha escrito nada)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
