"""Crea la tabla `lead_contactos` y siembra el primer tick de cada lead.

Hasta ahora solo se guardaba `Lead.ultimo_contacto`, una sola fecha que se
sobrescribía. El panel de seguimiento necesita el histórico, así que a partir
de aquí cada contacto deja su fila.

La siembra importa: sin ella, al abrir un lead que llevas meses trabajando
verías la lista de ticks vacía, como si nunca hubieras hablado con él. Se crea
un tick con la fecha que ya teníamos guardada, que es lo único que sabemos con
certeza de su pasado.

Es idempotente: si un lead ya tiene ticks, no se toca.

Uso (desde /var/www/freeagent):
    .venv/bin/python3 scripts/migrar_contactos.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine, SessionLocal, Base
from app import models  # noqa: F401  — registra los modelos en el metadata
from app.models import Lead, LeadContacto


def main() -> int:
    # create_all solo crea lo que falta; no toca las tablas que ya existen.
    Base.metadata.create_all(engine)
    print("Tabla lead_contactos: lista")

    db = SessionLocal()
    try:
        sembrados = saltados = 0
        for lead in db.query(Lead).all():
            if db.query(LeadContacto).filter(LeadContacto.lead_id == lead.id).count():
                saltados += 1
                continue
            db.add(LeadContacto(
                lead_id=lead.id,
                fecha=lead.ultimo_contacto or lead.created_at,
            ))
            sembrados += 1
        db.commit()
        print(f"Ticks sembrados: {sembrados} · leads que ya tenían: {saltados}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
