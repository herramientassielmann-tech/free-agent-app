"""Añade a la tabla `scripts` las columnas que usa el editor de guiones.

`Base.metadata.create_all` crea tablas nuevas (starter_script_edits sale sola),
pero no añade columnas a una tabla que ya existe. Estas dos hay que meterlas
a mano, una sola vez, antes de reiniciar el servicio.

Es idempotente: si las columnas ya están, no hace nada.

Uso (desde /var/www/freeagent):
    .venv/bin/python3 scripts/migrar_editor.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text
from app.database import engine, Base
from app import models  # noqa: F401  — registra los modelos en el metadata

COLUMNAS = {
    "edicion": "TEXT",
    "edited_at": "TIMESTAMP",
}


def main():
    inspector = inspect(engine)

    if "scripts" not in inspector.get_table_names():
        print("La tabla 'scripts' no existe todavía; create_all la creará completa.")
    else:
        existentes = {c["name"] for c in inspector.get_columns("scripts")}
        with engine.begin() as con:
            for nombre, tipo in COLUMNAS.items():
                if nombre in existentes:
                    print(f"  scripts.{nombre}: ya existe, se salta")
                    continue
                con.execute(text(f"ALTER TABLE scripts ADD COLUMN {nombre} {tipo}"))
                print(f"  scripts.{nombre}: AÑADIDA ({tipo})")

    # Crea starter_script_edits (y cualquier otra tabla que falte)
    Base.metadata.create_all(bind=engine)
    tablas = set(inspect(engine).get_table_names())
    print(f"\nstarter_script_edits: {'OK' if 'starter_script_edits' in tablas else 'FALTA'}")

    cols = {c["name"] for c in inspect(engine).get_columns("scripts")}
    faltan = set(COLUMNAS) - cols
    print(f"columnas del editor en 'scripts': {'OK' if not faltan else 'FALTAN ' + str(faltan)}")
    print("\nHecho. Ya se puede reiniciar el servicio.")


if __name__ == "__main__":
    main()
