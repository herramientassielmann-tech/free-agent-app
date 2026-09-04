"""Da de alta en la app los clips ya subidos a Drive.

Lee el JSON que genera el proceso de recorte y subida, y lo vuelca en la tabla
clips_reunion. Es idempotente: identifica cada clip por su id de Drive, así que
relanzarlo actualiza los que cambien y no duplica nada.

Uso (desde /var/www/freeagent):
    .venv/bin/python3 scripts/cargar_biblioteca.py clips_para_bd.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal, engine
from app.models import Base, ClipReunion


def main():
    if len(sys.argv) < 2:
        print("Falta el fichero JSON con los clips.")
        return 1
    origen = Path(sys.argv[1])
    if not origen.exists():
        print(f"No existe {origen}")
        return 1

    Base.metadata.create_all(bind=engine)
    filas = json.loads(origen.read_text(encoding="utf-8"))
    db = SessionLocal()
    nuevos = actualizados = 0

    try:
        for f in filas:
            clip = db.query(ClipReunion).filter(
                ClipReunion.drive_id == f["drive_id"]
            ).first()
            campos = dict(
                alumno=f["alumno"],
                titulo=f["titulo"],
                resumen=f.get("resumen") or None,
                tema=f.get("tema") or None,
                fecha_reunion=f["fecha"],
                inicio_seg=int(f["inicio"]),
                duracion_seg=int(f["duracion"]),
                tipo=f["tipo"],
                drive_id=f["drive_id"],
                drive_url=f["drive_url"],
                carpeta_url=f.get("carpeta_url"),
            )
            if clip:
                for k, v in campos.items():
                    setattr(clip, k, v)
                actualizados += 1
            else:
                db.add(ClipReunion(**campos))
                nuevos += 1
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    total = db.query(ClipReunion).count()
    por_alumno = {}
    for c in db.query(ClipReunion).all():
        por_alumno[c.alumno] = por_alumno.get(c.alumno, 0) + 1
    db.close()

    print(f"Nuevos: {nuevos} · actualizados: {actualizados}")
    print(f"Total en la biblioteca: {total}")
    for a, n in sorted(por_alumno.items()):
        print(f"  {a}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
