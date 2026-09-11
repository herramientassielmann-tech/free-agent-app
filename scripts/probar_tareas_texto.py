"""Comprueba el analizador de frases del gestor de tareas.

No hay marco de pruebas en el proyecto, así que esto es un script que se ejecuta
y dice si algo se ha roto. Merece la pena tenerlo porque el analizador es la
pieza donde más fácil es meter un fallo silencioso: que «viernes» caiga en el
viernes que no es no lo nota nadie hasta que alguien se pierde una llamada.

La fecha va fija a un viernes concreto: si dependiera del día en que se ejecuta,
la mitad de los casos darían distinto cada semana y el script no valdría nada.

Uso:
    .venv/bin/python3 scripts/probar_tareas_texto.py
"""
import sys
from collections import namedtuple
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.tareas_texto import analizar

P = namedtuple("P", "id name")
EQUIPO = [P(1, "Robert Sielmann"), P(2, "David Marín"), P(3, "Kevin Ortega")]
VIERNES = date(2026, 9, 11)

# (frase, texto, responsable, fecha, prioridad)
CASOS = [
    ("Pedir testimonio a Ada @david mañana !!", "Pedir testimonio a Ada", 2, date(2026, 9, 12), "urgente"),
    ("Llamar a Lilliana", "Llamar a Lilliana", None, None, "normal"),
    ("@kevin revisar el panel hoy", "revisar el panel", 3, VIERNES, "normal"),
    # Hoy ES viernes: quien lo apunta se refiere a hoy, no a dentro de una semana
    ("Preparar la grupal viernes", "Preparar la grupal", None, VIERNES, "normal"),
    ("Llamar al gestor lunes", "Llamar al gestor", None, date(2026, 9, 14), "normal"),
    ("Renovar dominio 25/09", "Renovar dominio", None, date(2026, 9, 25), "normal"),
    # Sin año y ya pasada: se entiende del año que viene
    ("Pagar impuestos 05/03", "Pagar impuestos", None, date(2027, 3, 5), "normal"),
    ("Cerrar el mes 31-12-2026", "Cerrar el mes", None, date(2026, 12, 31), "normal"),
    ("Revisar contrato en 3 días", "Revisar contrato", None, date(2026, 9, 14), "normal"),
    ("Mandar factura en 2 semanas", "Mandar factura", None, date(2026, 9, 25), "normal"),
    ("Llamar a Ada la semana que viene", "Llamar a Ada", None, date(2026, 9, 18), "normal"),
    ("Subir reel pasado mañana", "Subir reel", None, date(2026, 9, 13), "normal"),
    ("Cosa sin prisa !baja", "Cosa sin prisa", None, None, "baja"),
    ("@Kevin con mayúscula", "con mayúscula", 3, None, "normal"),
    # Una cuenta de Instagram no es un compañero: se queda en el texto
    ("Responder a @adarealty en Instagram", "Responder a @adarealty en Instagram", None, None, "normal"),
    ("miercoles sin tilde", "sin tilde", None, date(2026, 9, 16), "normal"),
    ("Llamar el sábado", "Llamar", None, date(2026, 9, 12), "normal"),
    ("Fecha imposible 45/13", "Fecha imposible 45/13", None, None, "normal"),
    # Si al quitarlo todo no queda nada, se guarda la frase original
    ("@david", "@david", 2, None, "normal"),
    ("  Espacios   raros   @robert  ", "Espacios raros", 1, None, "normal"),
]


def main() -> int:
    fallos = []
    for frase, texto, quien, fecha, prio in CASOS:
        r = analizar(frase, EQUIPO, hoy=VIERNES)
        esperado = {"texto": texto, "asignado_a": quien,
                    "fecha_limite": fecha, "prioridad": prio}
        if r != esperado:
            fallos.append((frase, esperado, r))

    for frase, esperado, obtenido in fallos:
        print(f"FALLA: {frase!r}")
        for k in esperado:
            if esperado[k] != obtenido[k]:
                print(f"   {k}: esperaba {esperado[k]!r}, salió {obtenido[k]!r}")

    print(f"{len(CASOS) - len(fallos)}/{len(CASOS)} correctos")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
