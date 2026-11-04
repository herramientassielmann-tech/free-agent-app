"""El guion por tomas, adaptado al formato del vídeo.

Los realtors graban así: leen un trozo corto, lo dicen de memoria a cámara y
pasan al siguiente. Por eso el guion no va en tres párrafos sino en bloques,
cada uno una toma, y con un diseño distinto según el formato del vídeo:

- lista:    elementos numerados, concepto y veredicto («Oro → invierte»).
- pares:    situación → qué hacer, en dos columnas.
- dialogo:  lo que dice el realtor (tú) y lo que dice otro o va en pantalla.
- adivina:  pregunta, pistas, respuesta.
- historia: hook, el desarrollo en tomas y el CTA. El de por defecto.

El modelo devuelve los bloques; hook, desarrollo y CTA se DERIVAN de ellos, para
que todo lo que ya lee esos tres campos (historial, copiar, recientes, el chat
de Robert) siga funcionando sin enterarse de nada."""
from typing import Optional

TIPOS = ("lista", "pares", "dialogo", "adivina", "historia")
PARTES = ("hook", "desarrollo", "cta")
ROLES = ("pista", "respuesta")
MAX_BLOQUES = 40
MAX_TEXTO = 1500


def _texto(valor) -> str:
    return " ".join(str(valor or "").split())[:MAX_TEXTO]


def normalizar(raw) -> Optional[dict]:
    """El formato limpio y con solo lo que la interfaz sabe pintar, o None si
    no queda nada utilizable. Tolerante: lo raro se reconduce, no se rechaza."""
    if not isinstance(raw, dict):
        return None
    tipo = raw.get("tipo") if raw.get("tipo") in TIPOS else "historia"

    bloques = []
    for b in (raw.get("bloques") or [])[:MAX_BLOQUES]:
        if not isinstance(b, dict):
            continue
        texto = _texto(b.get("texto"))
        extra = _texto(b.get("extra")) if tipo in ("lista", "pares") else ""
        if not texto and not extra:
            continue
        bloque = {
            "parte": b.get("parte") if b.get("parte") in PARTES else "desarrollo",
            "texto": texto,
        }
        if extra:
            bloque["extra"] = extra
        if tipo == "dialogo":
            bloque["quien"] = "otro" if b.get("quien") == "otro" else "tu"
        if tipo == "adivina" and b.get("rol") in ROLES:
            bloque["rol"] = b["rol"]
        bloques.append(bloque)

    if not bloques:
        return None
    formato = {"tipo": tipo, "bloques": bloques}
    if tipo == "pares":
        cols = [_texto(c)[:40] for c in (raw.get("columnas") or [])][:2]
        formato["columnas"] = cols if len(cols) == 2 and all(cols) else ["SITUACIÓN", "QUÉ HACER"]
    return formato


def _linea(tipo: str, b: dict) -> str:
    texto, extra = b.get("texto", ""), b.get("extra", "")
    if extra:
        separador = " → " if tipo == "pares" else ": "
        return f"{texto}{separador}{extra}" if texto else extra
    if tipo == "dialogo" and b.get("quien") == "otro":
        return f"— {texto}"
    return texto


def derivar_secciones(formato: dict) -> dict:
    """hook / development / conclusion en texto, una toma por línea."""
    tipo = formato.get("tipo", "historia")
    por_parte = {p: [] for p in PARTES}
    for b in formato.get("bloques", []):
        por_parte[b["parte"]].append(_linea(tipo, b))
    return {
        "hook": "\n".join(por_parte["hook"]),
        "development": "\n".join(por_parte["desarrollo"]),
        "conclusion": "\n".join(por_parte["cta"]),
    }


def usa_formato(user) -> bool:
    """Quién genera ya por tomas. De momento solo el admin, como piloto: para
    abrirlo a todos, se cambia aquí y en ningún otro sitio."""
    return bool(user.is_admin)
