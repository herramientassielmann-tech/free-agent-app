import json
import re
import unicodedata
import anthropic
from typing import Optional
from app.config import ANTHROPIC_API_KEY
from app.models import RealtorProfile

SPEC = {
    "primera_vivienda": "primera vivienda y compradores primerizos",
    "lujo": "propiedades de lujo y alto standing",
    "inversion": "inversión inmobiliaria y rentabilidad",
    "comercial": "inmuebles comerciales y locales",
    "todo_tipo": "todo tipo de propiedades y clientes",
}

# Palabras que el handle NUNCA puede contener (blindaje aparte del prompt,
# porque el modelo puede fallar la instrucción). El handle es solo el nombre.
FORBIDDEN_HANDLE_SUBSTRINGS = [
    "realestate", "real_estate", "realtor", "inmobiliaria", "broker",
    "bienesraices", "bienesraiz", "realty", "properties", "propiedades",
]

_SYSTEM = """Eres un experto en marca personal y en SEO de Instagram para agentes inmobiliarios (realtors). Optimizas su perfil para MÁXIMA conversión de leads y para que el buscador de Instagram los posicione.

Con los datos del realtor (y su bio actual y/o una captura de su perfil, si te la doy) generas 3 VERSIONES optimizadas del perfil, cada una con un ángulo ligeramente distinto, pero todas fieles a su nicho, su zona y su cliente ideal.

Si se te adjunta una IMAGEN del perfil de Instagram actual, MÍRALA PRIMERO: el nombre completo (nombre y apellido) escrito en el campo "Nombre" del perfil (la línea en negrita, distinta del @usuario) es la fuente de verdad definitiva sobre su nombre real. Úsalo aunque el "Nombre real" que te doy en los datos esté incompleto (por ejemplo, solo el nombre de pila).

CADA VERSIÓN tiene estas 4 piezas:

1) handle — el nombre de usuario público. SIEMPRE es el NOMBRE REAL COMPLETO de la persona (nombre + apellido, si lo conoces) junto, en minúsculas y sin espacios. PROHIBIDO TERMINANTE: nunca añadas "realestate", "real estate", "realtor", "inmobiliaria", "broker", "realty" ni ninguna palabra del nicho, la ciudad o el negocio — el handle es SOLO su nombre de persona, nada más. Como el handle exacto puede estar ya cogido en Instagram, entre las 3 versiones da variantes usando SOLO pequeños trucos sobre su propio nombre: doblar la última letra, añadir un guion bajo, o un punto entre nombre y apellido. Ejemplo para "Ada Bonilla": "adabonilla", "adabonillaa", "ada.bonilla". El handle siempre se lee claramente como su nombre real.

2) nombre — el campo "Nombre" de Instagram (lo que de verdad indexa el buscador). Formato: NOMBRE REAL COMPLETO (nombre + apellido, SIEMPRE que lo conozcas) + separador " | " + palabra(s) clave de zona y nicho por las que quieres que le encuentren. Ejemplos: "Ada Bonilla | Miami Real Estate", "Ada Bonilla | Preservación de Capitales". Nunca uses solo el nombre de pila si conoces el apellido. Corto y con keywords buscables.

3) bio — EXACTAMENTE 3 frases, en este orden:
   - Frase 1: en qué es experto/a.
   - Frase 2: a quién ayuda y con qué beneficio.
   - Frase 3: un CTA hacia el enlace de abajo (que es su teléfono). Ej: "Habla conmigo", "Contáctame".
   Cada frase EMPIEZA con UN solo emoji (nunca más de uno, y solo al principio de la frase). MUY IMPORTANTE: cada frase tiene un MÁXIMO de 45 caracteres en total, contando el emoji y los espacios. Cuenta los caracteres de cada frase y recórtala si se pasa. Frases telegráficas, claras y orientadas a conversión. Sin relleno.

4) enlace — SIEMPRE el teléfono del realtor (te lo doy). No lo cambies.

Escribe en español, natural y cercano.

FORMATO DE RESPUESTA (JSON estricto, sin texto adicional):
{
  "opciones": [
    {"handle": "...", "nombre": "...", "bio": ["🏡 ...", "🤝 ...", "📲 ..."], "enlace": "<telefono>"},
    {"handle": "...", "nombre": "...", "bio": ["...", "...", "..."], "enlace": "<telefono>"},
    {"handle": "...", "nombre": "...", "bio": ["...", "...", "..."], "enlace": "<telefono>"}
  ]
}"""


def ig_handle_from_link(link: str) -> str:
    """Extrae el @handle de un link de Instagram (o lo deja tal cual si ya es un handle)."""
    link = (link or "").strip()
    if not link:
        return ""
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]+)", link)
    if m:
        return m.group(1)
    return link.lstrip("@").strip("/")


def _split_name_words(name: str) -> list:
    """'Ada Bonilla' -> ['ada', 'bonilla'] (sin acentos ni símbolos)."""
    name = unicodedata.normalize("NFKD", name or "")
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^a-zA-Z\s]", " ", name)
    return [w.lower() for w in name.split() if w]


def _handle_variant(base: str, words: list, index: int) -> str:
    """Genera un handle limpio derivado del nombre real, sin depender del modelo."""
    if not base:
        return base
    if index == 0:
        return base
    if index == 1:
        return base[:-1] + base[-1] * 2
    if len(words) >= 2:
        return words[0] + "." + "".join(words[1:])
    return base + "_"


def _is_valid_handle(handle: str, base: str) -> bool:
    """El handle no debe llevar palabras del negocio y debe derivarse del nombre real."""
    h = re.sub(r"[._]", "", (handle or "").lower().lstrip("@"))
    if not h or not base:
        return False
    for bad in FORBIDDEN_HANDLE_SUBSTRINGS:
        if bad in h:
            return False
    if base in h or h in base:
        return True
    if len(base) > 3 and base[:-1] in h:  # tolera la letra doblada/recortada
        return True
    return False


def optimize_ig_profile(
    nombre: str,
    profile: Optional[RealtorProfile],
    current_bio: str = "",
    current_handle: str = "",
    screenshot_base64: Optional[str] = None,
    screenshot_media_type: Optional[str] = None,
) -> list:
    """Genera 3 versiones optimizadas del perfil de Instagram del realtor."""
    market = (profile.market if profile else None) or "su zona"
    spec_key = (profile.specialization if profile else "todo_tipo") or "todo_tipo"
    spec = SPEC.get(spec_key, SPEC["todo_tipo"])
    telefono = (profile.telefono if profile else None) or ""

    def campo(v):
        return (v or "").strip() or "(no especificado)"

    imagen_nota = (
        "\n- Se adjunta una captura del perfil de Instagram actual: MÍRALA. "
        "El nombre completo (con apellido) que aparece escrito ahí es la fuente "
        "de verdad definitiva, aunque sea distinto o más completo que el "
        '"Nombre real" de arriba.'
        if screenshot_base64 else ""
    )

    datos = f"""DATOS DEL REALTOR:
- Nombre real (puede estar incompleto, p.ej. solo el nombre de pila): {nombre}
- Zona/mercado: {market}
- Especialización: {spec}
- Cliente ideal: {campo(profile.cliente_ideal if profile else "")}
- A quién ayuda / dolores que resuelve: {campo(profile.objeciones if profile else "")}
- Casos de éxito: {campo(profile.casos_exito if profile else "")}
- Objetivo / CTA preferido: {campo(profile.objetivo_cta if profile else "")}
- Contexto: {campo(profile.about_me if profile else "")}
- Teléfono (este es el enlace de abajo): {telefono or "(no especificado)"}
- Handle actual de Instagram: {current_handle or "(no especificado)"}
- Bio actual de Instagram: {current_bio.strip() or "(no especificada)"}{imagen_nota}

Genera las 3 versiones optimizadas en el formato JSON indicado. El enlace de cada versión debe ser exactamente el teléfono indicado."""

    content = []
    if screenshot_base64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": screenshot_media_type or "image/jpeg",
                "data": screenshot_base64,
            },
        })
    content.append({"type": "text", "text": datos})

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": content}],
    )

    raw = message.content[0].text.strip()
    json_start = raw.find("{")
    json_end = raw.rfind("}") + 1
    if json_start == -1 or json_end == 0:
        raise ValueError("La respuesta de la IA no contiene JSON válido.")
    parsed = json.loads(raw[json_start:json_end])

    opciones = parsed.get("opciones", [])
    if not isinstance(opciones, list) or not opciones:
        raise ValueError("La IA no devolvió opciones válidas.")

    # Normalizar: garantizar handle/nombre/bio(3)/enlace(=teléfono)
    limpias = []
    for op in opciones[:3]:
        bio = op.get("bio", [])
        if isinstance(bio, str):
            bio = [b.strip() for b in bio.split("\n") if b.strip()]
        bio = [str(b).strip() for b in bio][:3]
        limpias.append({
            "handle": str(op.get("handle", "")).strip().lstrip("@"),
            "nombre": str(op.get("nombre", "")).strip(),
            "bio": bio,
            # El enlace SIEMPRE es el teléfono real (o vacío) — nunca algo inventado por el modelo.
            "enlace": telefono.strip() if telefono else "",
        })

    # Blindaje: el handle SIEMPRE se deriva del nombre real y nunca lleva
    # palabras del negocio, aunque el modelo se equivoque.
    for idx, op in enumerate(limpias):
        real_name = (op["nombre"].split("|")[0].strip() if op["nombre"] else "") or nombre
        words = _split_name_words(real_name)
        base = "".join(words)
        if base and not _is_valid_handle(op["handle"], base):
            op["handle"] = _handle_variant(base, words, idx)

    return limpias
