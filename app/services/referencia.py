"""Partir la transcripción del vídeo de referencia en hook, desarrollo y CTA.

La transcripción se enseña tal cual, sin adaptar. Por eso el modelo no la
reescribe: solo dice DÓNDE empieza el desarrollo y dónde el CTA, copiando unas
palabras literales del texto, y el corte se hace aquí sobre el original. Así es
imposible que se cuele una palabra cambiada o que se pierda una frase."""
import json
import re
from typing import Optional

import anthropic

from app.config import ANTHROPIC_API_KEY

SISTEMA = """Te paso la transcripción de un vídeo corto de redes sociales. Tienes que decir dónde empieza cada parte:
- HOOK: la primera frase o frases, las que enganchan. Nunca está vacío: como mínimo es la primera frase, aunque el vídeo sea una lista.
- DESARROLLO: el cuerpo del vídeo.
- CTA: el llamamiento final (sígueme, escríbeme, comenta, contáctame...). Puede no haberlo.

El desarrollo NUNCA empieza en la primera palabra del texto. NO reescribas ni traduzcas nada. Copia LITERALMENTE, carácter por carácter, las primeras 5 a 8 palabras con las que empieza el desarrollo, y las primeras 5 a 8 con las que empieza el CTA. Si no hay CTA, deja "inicio_cta" vacío.

Responde SOLO con este JSON:
{"inicio_desarrollo": "...", "inicio_cta": "..."}"""


def _buscar(texto: str, trozo: str, desde: int = 0) -> int:
    """Posición de `trozo` en `texto`, sin que importen mayúsculas ni espacios
    de más (el modelo a veces se los come). -1 si no está."""
    palabras = trozo.split()
    if not palabras:
        return -1
    patron = r"\s+".join(re.escape(p) for p in palabras)
    m = re.compile(patron, re.IGNORECASE).search(texto, desde)
    return m.start() if m else -1


def partir(transcripcion: str) -> Optional[dict]:
    """{"hook", "desarrollo", "cta"} con el texto original troceado, o None si
    no se ha podido partir con seguridad (entonces se enseña de un bloque).

    Lanza la excepción si falla la llamada a la API, para que quien llame no
    lo confunda con «no se puede partir» y lo vuelva a intentar otro día."""
    texto = (transcripcion or "").strip()
    if not texto:
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=SISTEMA,
        messages=[{"role": "user", "content": texto[:12000]}],
    )
    bloque = next((b for b in msg.content if b.type == "text"), None)
    bruto = bloque.text if bloque else ""
    try:
        datos = json.loads(bruto[bruto.find("{"): bruto.rfind("}") + 1])
    except ValueError:
        return None

    i_des = _buscar(texto, str(datos.get("inicio_desarrollo") or ""))
    if i_des == 0:
        # Ha metido todo en el desarrollo (pasa en los vídeos de lista): el hook
        # llega hasta el primer punto que deje al menos seis palabras, para que
        # no se quede en una sola («Gold.»).
        i_des = -1
        for fin in re.finditer(r"[.!?…](\s+|$)", texto):
            if len(texto[:fin.end()].split()) >= 6:
                i_des = fin.end() if fin.end() < len(texto) else -1
                break
    if i_des <= 0:
        return None
    i_cta = _buscar(texto, str(datos.get("inicio_cta") or ""), i_des + 1)
    if i_cta < 0:
        i_cta = len(texto)

    partes = {
        "hook": texto[:i_des].strip(),
        "desarrollo": texto[i_des:i_cta].strip(),
        "cta": texto[i_cta:].strip(),
    }
    if not partes["hook"] or not partes["desarrollo"]:
        return None
    return partes
