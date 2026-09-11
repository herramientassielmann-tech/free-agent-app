"""Saca de una frase suelta el responsable, la fecha y la prioridad.

«Pedir testimonio a Ada @david mañana !!» se convierte en una tarea con dueño,
fecha y urgencia. Es el centro del gestor de tareas: los mejores gestores del
mundo coinciden en que la diferencia entre escribir una línea y pasar por cuatro
menús es la diferencia entre un sistema que se usa y uno que se abandona.

Vive aquí y no dentro del router porque es puro —entra texto, sale un
diccionario, no toca la base de datos— y porque es donde más fácil es meter un
fallo sutil: que «viernes» caiga en el viernes equivocado no lo ve nadie hasta
que alguien se pierde una llamada. Aislado se puede probar de verdad.

Sin librería a propósito. `dateparser` haría esto y más, pero producción tiene
hoy 16 paquetes y esto son cuarenta líneas.
"""
import re
import unicodedata
from datetime import date, timedelta
from typing import List, Optional

PRIORIDADES = ("urgente", "normal", "baja")
ESTADOS = ("pendiente", "hecha")

# El equipo son tres nombres, no tres cuentas: los tres entran con el mismo
# usuario de administrador. El responsable es una etiqueta, y por eso se guarda
# el nombre y no un identificador de usuario.
EQUIPO = ("Robert", "David", "Kevin")

# Los acentos se aceptan escritos o no: nadie va a poner «miércoles» con tilde
# mientras apunta algo deprisa.
DIAS = {
    r"lunes": 0, r"martes": 1, r"mi[ée]rcoles": 2, r"jueves": 3,
    r"viernes": 4, r"s[áa]bado": 5, r"domingo": 6,
}


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def _quitar(texto: str, patron: str) -> tuple:
    """Corta del texto la primera aparición del patrón. (texto_limpio, encontrado)"""
    m = re.search(patron, texto, re.IGNORECASE)
    if not m:
        return texto, None
    return (texto[:m.start()] + " " + texto[m.end():]), m


def _proximo_dia(hoy: date, indice: int) -> date:
    """El próximo día de la semana con ese número.

    Si hoy ES ese día, devuelve hoy y no el de la semana que viene: quien apunta
    «llamar el viernes» un viernes por la mañana se refiere a hoy.
    """
    faltan = (indice - hoy.weekday()) % 7
    return hoy + timedelta(days=faltan)


def _fecha_suelta(texto: str, hoy: date) -> tuple:
    """Busca una fecha escrita como 25/09 o 25-09-2026."""
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", texto)
    if not m:
        return texto, None
    dia, mes = int(m.group(1)), int(m.group(2))
    anio = m.group(3)
    if anio:
        anio = int(anio)
        if anio < 100:
            anio += 2000
    else:
        anio = hoy.year
    try:
        d = date(anio, mes, dia)
    except ValueError:
        return texto, None          # 45/13 no es una fecha: se queda como texto
    # Sin año, una fecha ya pasada se entiende del año que viene
    if not m.group(3) and d < hoy:
        try:
            d = d.replace(year=anio + 1)
        except ValueError:
            return texto, None      # 29/02 de un año no bisiesto
    return (texto[:m.start()] + " " + texto[m.end():]), d


def _fecha(texto: str, hoy: date) -> tuple:
    """Devuelve (texto_sin_la_fecha, fecha) o (texto, None)."""
    # Lo más específico primero: «pasado mañana» antes que «mañana», y
    # «la semana que viene» antes de que «semana» se coma otra cosa.
    texto2, m = _quitar(texto, r"\bpasado\s+ma[ñn]ana\b")
    if m:
        return texto2, hoy + timedelta(days=2)

    texto2, m = _quitar(texto, r"\b(?:la\s+)?(?:pr[óo]xima\s+semana|semana\s+que\s+viene)\b")
    if m:
        return texto2, hoy + timedelta(days=7)

    texto2, m = _quitar(texto, r"\ben\s+(\d+|una?|dos|tres)\s+(d[íi]as?|semanas?)\b")
    if m:
        palabras = {"un": 1, "una": 1, "dos": 2, "tres": 3}
        n = palabras.get(m.group(1).lower(), None)
        if n is None:
            n = int(m.group(1))
        dias = n * (7 if m.group(2).lower().startswith("semana") else 1)
        return texto2, hoy + timedelta(days=dias)

    texto2, m = _quitar(texto, r"\bhoy\b")
    if m:
        return texto2, hoy

    texto2, m = _quitar(texto, r"\bma[ñn]ana\b")
    if m:
        return texto2, hoy + timedelta(days=1)

    for patron, indice in DIAS.items():
        texto2, m = _quitar(texto, rf"\b(?:el\s+)?{patron}\b")
        if m:
            return texto2, _proximo_dia(hoy, indice)

    return _fecha_suelta(texto, hoy)


def _responsable(texto: str, equipo) -> tuple:
    """Busca @alguien y lo empareja con un nombre del equipo.

    Si no coincide con nadie se deja tal cual en el texto: «responder a
    @adarealty» es una cuenta de Instagram, no un compañero, y borrarla se
    cargaría la tarea.
    """
    for m in re.finditer(r"@([\wáéíóúñ]+)", texto, re.IGNORECASE):
        buscado = _sin_acentos(m.group(1))
        exactos = [n for n in equipo if _sin_acentos(n) == buscado]
        if not exactos:
            exactos = [n for n in equipo if _sin_acentos(n).startswith(buscado)]
        if len(exactos) == 1:
            return (texto[:m.start()] + " " + texto[m.end():]), exactos[0]
    return texto, None


def analizar(texto: str, equipo=EQUIPO, hoy: Optional[date] = None) -> dict:
    """Convierte una frase en los campos de una tarea.

    `equipo` es una lista de nombres. `hoy` se puede pasar para probar esto sin
    depender del día en que se ejecute.
    """
    hoy = hoy or date.today()
    original = (texto or "").strip()

    resto = original
    prioridad = "normal"

    resto2, m = _quitar(resto, r"(?:^|\s)!!(?=\s|$)")
    if m:
        resto, prioridad = resto2, "urgente"
    else:
        resto2, m = _quitar(resto, r"(?:^|\s)!(?:baja|b)(?=\s|$)")
        if m:
            resto, prioridad = resto2, "baja"

    resto, asignado = _responsable(resto, equipo)
    resto, fecha = _fecha(resto, hoy)

    limpio = re.sub(r"\s{2,}", " ", resto).strip(" ,.;-")
    return {
        # Si al quitarlo todo no queda nada, vale más guardar la frase original
        # que una tarea en blanco.
        "texto": (limpio or original)[:300],
        "asignado_a": asignado,
        "fecha_limite": fecha,
        "prioridad": prioridad,
    }
