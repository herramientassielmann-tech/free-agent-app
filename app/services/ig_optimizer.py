import json
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

_SYSTEM = """Eres un experto en marca personal y en SEO de Instagram para agentes inmobiliarios (realtors). Optimizas su perfil para MÁXIMA conversión de leads y para que el buscador de Instagram los posicione.

Con los datos del realtor (y su bio actual si la hay) generas 3 VERSIONES optimizadas del perfil, cada una con un ángulo ligeramente distinto, pero todas fieles a su nicho, su zona y su cliente ideal.

CADA VERSIÓN tiene estas 4 piezas:

1) handle — el nombre de usuario público. SIEMPRE es su NOMBRE REAL COMPLETO (nombre + apellido) junto, en minúsculas y sin espacios. NUNCA añadas "realtor", "realestate", el nicho, la ciudad ni ninguna palabra que no sea su nombre. Como el handle exacto puede estar ya cogido en Instagram, entre las 3 versiones da variantes usando SOLO pequeños trucos sobre su propio nombre: doblar la última letra, añadir un guion bajo (al final o al principio), o un punto entre nombre y apellido. Ejemplo para "Ada Bonilla": "adabonilla", "adabonillaa", "adabonilla_" (también valen "ada.bonilla" o "_adabonilla"). El handle siempre tiene que leerse claramente como su nombre real.

2) nombre — el campo "Nombre" de Instagram (lo que de verdad indexa el buscador). Formato: Nombre real + separador " | " + palabra(s) clave de zona y nicho por las que quieres que le encuentren. Ejemplos: "Ada Ruiz | Miami Real Estate", "Ada Ruiz | Preservación de Capitales". Corto y con keywords buscables.

3) bio — EXACTAMENTE 3 frases, en este orden:
   - Frase 1: en qué es experto/a.
   - Frase 2: a quién ayuda y con qué beneficio.
   - Frase 3: un CTA hacia el enlace de abajo (que es su teléfono). Ej: "Habla conmigo", "Contáctame".
   Cada frase EMPIEZA con UN solo emoji (nunca más de uno, y solo al principio de la frase). Frases cortas, claras y orientadas a conversión. Sin relleno ni frases genéricas.

4) enlace — SIEMPRE el teléfono del realtor (te lo doy). No lo cambies.

Escribe en español, natural y cercano. Puedes mantener keywords de SEO estándar del nicho (como "Real Estate") si es como se busca en su mercado.

FORMATO DE RESPUESTA (JSON estricto, sin texto adicional):
{
  "opciones": [
    {"handle": "...", "nombre": "...", "bio": ["🏡 ...", "🤝 ...", "📲 ..."], "enlace": "<telefono>"},
    {"handle": "...", "nombre": "...", "bio": ["...", "...", "..."], "enlace": "<telefono>"},
    {"handle": "...", "nombre": "...", "bio": ["...", "...", "..."], "enlace": "<telefono>"}
  ]
}"""


def optimize_ig_profile(
    nombre: str,
    profile: Optional[RealtorProfile],
    current_bio: str = "",
    current_handle: str = "",
) -> list:
    """Genera 3 versiones optimizadas del perfil de Instagram del realtor."""
    market = (profile.market if profile else None) or "su zona"
    spec_key = (profile.specialization if profile else "todo_tipo") or "todo_tipo"
    spec = SPEC.get(spec_key, SPEC["todo_tipo"])
    telefono = (profile.telefono if profile else None) or ""

    def campo(v):
        return (v or "").strip() or "(no especificado)"

    datos = f"""DATOS DEL REALTOR:
- Nombre real: {nombre}
- Zona/mercado: {market}
- Especialización: {spec}
- Cliente ideal: {campo(profile.cliente_ideal if profile else "")}
- A quién ayuda / dolores que resuelve: {campo(profile.objeciones if profile else "")}
- Casos de éxito: {campo(profile.casos_exito if profile else "")}
- Objetivo / CTA preferido: {campo(profile.objetivo_cta if profile else "")}
- Contexto: {campo(profile.about_me if profile else "")}
- Teléfono (este es el enlace de abajo): {telefono or "(no especificado)"}
- Handle actual de Instagram: {current_handle or "(no especificado)"}
- Bio actual de Instagram: {current_bio.strip() or "(no especificada)"}

Genera las 3 versiones optimizadas en el formato JSON indicado. El enlace de cada versión debe ser exactamente el teléfono indicado."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": datos}],
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
            "enlace": telefono or str(op.get("enlace", "")).strip(),
        })
    return limpias
