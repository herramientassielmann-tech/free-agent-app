import json
from typing import Optional
import anthropic
from app.config import ANTHROPIC_API_KEY
from app.models import User, RealtorProfile

TONE_DESCRIPTIONS = {
    "formal": "profesional y formal, con vocabulario técnico del sector inmobiliario",
    "cercano": "cercano y natural, como si hablaras con un amigo de confianza",
    "energetico": "energético y dinámico, con mucho entusiasmo y ritmo rápido",
    "inspiracional": "inspiracional y motivador, enfocado en sueños y cambios de vida",
}

SPECIALIZATION_DESCRIPTIONS = {
    "primera_vivienda": "primera vivienda y compradores primerizos",
    "lujo": "propiedades de lujo y alto standing",
    "inversion": "inversión inmobiliaria y rentabilidad",
    "comercial": "inmuebles comerciales y locales",
    "todo_tipo": "todo tipo de propiedades y clientes",
}


def _build_system_prompt(profile: Optional[RealtorProfile], user: User) -> str:
    name = (profile.display_name if profile and profile.display_name else user.name) or "Realtor"
    market = (profile.market if profile else None) or "España"
    tone_key = (profile.tone if profile else "cercano") or "cercano"
    tone_desc = TONE_DESCRIPTIONS.get(tone_key, TONE_DESCRIPTIONS["cercano"])
    spec_key = (profile.specialization if profile else "todo_tipo") or "todo_tipo"
    spec_desc = SPECIALIZATION_DESCRIPTIONS.get(spec_key, SPECIALIZATION_DESCRIPTIONS["todo_tipo"])
    speaking_notes = (profile.speaking_notes if profile else None) or ""
    about_me = (profile.about_me if profile else None) or ""

    profile_section = f"""
PERFIL DEL REALTOR:
- Nombre: {name}
- Mercado/zona: {market}
- Tono de comunicación: {tone_desc}
- Especialización: {spec_desc}
{"- Notas de estilo personal: " + speaking_notes if speaking_notes else ""}
{"- Sobre el realtor: " + about_me if about_me else ""}
""".strip()

    return f"""Eres un experto en marketing de contenido para el sector inmobiliario hispanohablante.
Tu tarea es transformar transcripciones de vídeos en guiones personalizados para un realtor específico.

{profile_section}

REGLAS INQUEBRANTABLES:
1. El resultado SIEMPRE debe estar en español, independientemente del idioma del vídeo original.
2. Si el vídeo NO es del nicho inmobiliario, debes adaptarlo al mundo del Real Estate manteniendo la estructura y el gancho original.
3. Si el vídeo YA es de Real Estate, personalízalo según el perfil del realtor.
4. Respeta la idea central y la estructura narrativa del vídeo original — copia el concepto con otras palabras, no inventes una historia nueva.
5. El formato es para vídeo vertical (Reels/TikTok/Shorts): Hook breve e impactante, Desarrollo claro, Conclusión con llamada a la acción.
6. El guión debe sonar NATURAL cuando se habla en voz alta, no como texto escrito.
7. El caption debe tener emojis relevantes, hashtags del sector inmobiliario en español y una llamada a la acción.

FORMATO DE RESPUESTA (JSON estricto, sin texto adicional):
{{
  "hook": "Texto del hook (máx 3 frases cortas y poderosas, pensado para los primeros 3 segundos)",
  "desarrollo": "Texto del desarrollo (el cuerpo del vídeo, natural y fluido)",
  "conclusion": "Texto de la conclusión con llamada a la acción clara",
  "caption": "Caption completo para la publicación con emojis y hashtags"
}}"""


def generate_script(
    transcript: str,
    user: User,
    profile: Optional[RealtorProfile],
    custom_instructions: str = "",
) -> dict:
    """
    Llama a Claude para generar Hook, Desarrollo, Conclusión y Caption
    a partir de una transcripción y el perfil del realtor.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    instructions_block = ""
    if custom_instructions.strip():
        instructions_block = f"""
INSTRUCCIONES ESPECÍFICAS DEL REALTOR:
{custom_instructions.strip()}

Ten en cuenta estas instrucciones al adaptar el guión (pueden referirse a una propiedad concreta, un mensaje específico, etc.).
"""

    user_message = f"""Aquí está la transcripción del vídeo original:

---
{transcript}
---
{instructions_block}
Genera el guión adaptado en el formato JSON indicado."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=_build_system_prompt(profile, user),
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()

    # Extraer JSON aunque Claude añada texto alrededor
    json_start = raw.find("{")
    json_end = raw.rfind("}") + 1
    if json_start == -1 or json_end == 0:
        raise ValueError("La respuesta de Claude no contiene JSON válido.")

    parsed = json.loads(raw[json_start:json_end])

    required_keys = {"hook", "desarrollo", "conclusion", "caption"}
    if not required_keys.issubset(parsed.keys()):
        raise ValueError(f"Faltan campos en la respuesta: {required_keys - parsed.keys()}")

    return parsed
