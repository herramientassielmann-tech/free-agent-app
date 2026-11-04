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


# ─────────────── El original por tomas, como el guion adaptado ───────────────

SISTEMA_TOMAS = """Te paso la transcripción ORIGINAL de un vídeo corto y la versión ADAPTADA del mismo vídeo, ya partida en tomas (bloques). Tienes que partir el ORIGINAL en tomas con la MISMA estructura, para poder comparar toma con toma: la toma 1 del original con la toma 1 de la adaptada, y así.

NO reescribas ni traduzcas nada. Para cada toma del original dices DÓNDE empieza, copiando LITERALMENTE, carácter por carácter, sus primeras 4 a 8 palabras tal como aparecen en el original.

Reglas:
- Mismo orden y, siempre que se pueda, el mismo número de tomas que la adaptada, con la misma "parte", "quien" y "rol" que su toma correspondiente.
- Una toma nunca empieza a mitad de frase.
- En "lista" y "pares", si la toma adaptada tiene "extra" (segunda columna), di también dónde empieza esa segunda columna en el original con "inicio_extra" (sus primeras palabras literales). Si no la tiene, no pongas "inicio_extra".

Responde SOLO con este JSON:
{"bloques": [{"inicio": "primeras palabras literales", "parte": "hook | desarrollo | cta", "quien": "tu | otro", "rol": "pista | respuesta", "inicio_extra": "solo en lista y pares"}]}"""


def partir_en_tomas(transcripcion: str, formato_adaptado: dict) -> Optional[dict]:
    """El original con la misma forma que el guion adaptado (mismo tipo, mismas
    tomas), o None si no se ha podido con seguridad: entonces se enseña en hook,
    desarrollo y CTA como siempre.

    Como en partir(), la IA solo dice dónde empieza cada toma y el corte se
    hace aquí sobre el original: el texto sale literal por construcción, juntas
    las tomas son exactamente la transcripción.

    Lanza la excepción si falla la llamada a la API, para reintentarlo."""
    from app.services import formato as formato_svc

    texto = (transcripcion or "").strip()
    if not texto or not formato_adaptado:
        return None
    tipo = formato_adaptado.get("tipo", "historia")
    guia = formato_adaptado.get("bloques", [])
    # La adaptada va como lista numerada y no en JSON: en JSON, el modelo copia
    # su forma (texto/extra) en vez de decir dónde empieza cada toma.
    adaptada = "\n".join(
        f'{n}. [{b.get("parte")}{"·" + b["quien"] if b.get("quien") else ""}'
        f'{"·" + b["rol"] if b.get("rol") else ""}] {b.get("texto", "")}'
        f'{" ‖ " + b["extra"] if b.get("extra") else ""}'
        for n, b in enumerate(guia, 1))

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=3000,
        system=SISTEMA_TOMAS,
        messages=[{"role": "user", "content":
                   f"ORIGINAL:\n{texto[:12000]}\n\nADAPTADA (tipo {tipo}):\n{adaptada}"}],
    )
    bloque = next((b for b in msg.content if b.type == "text"), None)
    bruto = bloque.text if bloque else ""
    try:
        datos = json.loads(bruto[bruto.find("{"): bruto.rfind("}") + 1])
    except ValueError:
        return None

    # Dónde empieza cada toma. Las que no se encuentren, o vayan hacia atrás,
    # se saltan: su texto queda dentro de la toma anterior y no se pierde nada.
    # El ancla: las primeras palabras de lo que devuelva (aunque mande la toma
    # entera en vez de su inicio), para que una palabra cambiada al final no
    # impida encontrarla.
    def ancla(valor, n=6):
        return " ".join(str(valor or "").split()[:n])

    respuesta = [b for b in (datos.get("bloques") or []) if isinstance(b, dict)]
    # Con el mismo número de tomas, la parte, la voz y el rol se copian de la
    # adaptada, que es la que manda; si no, los que diga el modelo.
    mismas = len(respuesta) == len(guia)
    cortes = []
    for n, b in enumerate(respuesta):
        desde = cortes[-1][0] + 1 if cortes else 0
        pos = 0 if not cortes else _buscar(texto, ancla(b.get("inicio") or b.get("texto")), desde)
        if pos < 0:
            continue
        meta = guia[n] if mismas else b
        cortes.append((pos, {**b, "parte": meta.get("parte"), "quien": meta.get("quien"),
                             "rol": meta.get("rol"), "con_extra": bool(guia[n].get("extra")) if mismas else bool(b.get("inicio_extra") or b.get("extra"))}))
    if not cortes:
        return None

    bloques = []
    for n, (pos, b) in enumerate(cortes):
        fin = cortes[n + 1][0] if n + 1 < len(cortes) else len(texto)
        trozo = texto[pos:fin].strip()
        nuevo = {"parte": b.get("parte"), "quien": b.get("quien"), "rol": b.get("rol"), "texto": trozo}
        if tipo in ("lista", "pares") and b["con_extra"]:
            # El concepto es la primera frase de la toma («Bitcoin.» | «Si no te
            # gusta arriesgar…»): más fiable que el ancla del modelo, que a veces
            # corta a media frase. Si no hay punto, entonces sí, el ancla.
            fin = re.search(r"[.!?…:](\s+)", trozo)
            i = fin.end() if fin else _buscar(trozo, ancla(b.get("inicio_extra") or b.get("extra"), 3))
            if 0 < i < len(trozo):
                nuevo["texto"], nuevo["extra"] = trozo[:i].strip(), trozo[i:].strip()
        bloques.append(nuevo)

    crudo = {"tipo": tipo, "bloques": bloques}
    if tipo == "pares":
        crudo["columnas"] = formato_adaptado.get("columnas")
    return formato_svc.normalizar(crudo)
