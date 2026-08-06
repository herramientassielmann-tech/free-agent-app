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
    cliente_ideal = (profile.cliente_ideal if profile else None) or ""
    objeciones = (profile.objeciones if profile else None) or ""
    casos_exito = (profile.casos_exito if profile else None) or ""
    objetivo_cta = (profile.objetivo_cta if profile else None) or ""
    temas_evitar = (profile.temas_evitar if profile else None) or ""

    lineas = [
        "PERFIL DEL REALTOR:",
        f"- Nombre: {name}",
        f"- Mercado/zona: {market}",
        f"- Tono: {tone_desc}",
        f"- Especialización: {spec_desc}",
    ]
    if speaking_notes:
        lineas.append(f"- Estilo personal (cómo habla): {speaking_notes}")
    if about_me:
        lineas.append(f"- Contexto y autoridad: {about_me}")
    if cliente_ideal:
        lineas.append(f"- Cliente ideal (a quién le habla): {cliente_ideal}")
    if objeciones:
        lineas.append(f"- Dolores y objeciones frecuentes de sus clientes (úsalos como munición para el HOOK): {objeciones}")
    if casos_exito:
        lineas.append(f"- Casos de éxito y cifras reales (úsalos como prueba social y concreción): {casos_exito}")
    if objetivo_cta:
        lineas.append(f"- Objetivo del contenido y CTA preferido (guía el CTA final): {objetivo_cta}")
    if temas_evitar:
        lineas.append(f"- Temas a evitar (NO los menciones): {temas_evitar}")
    profile_section = "\n".join(lineas)

    return f"""Eres el adaptador de guiones de vídeo de Free Agent Academy. Tu trabajo NO es crear un guión nuevo ni "mejorar" el vídeo: es ADAPTAR, palabra por palabra, una transcripción que ya existe, al mundo del realtor. Piénsalo como un doblaje o una localización: coges el vídeo original y lo "traduces" al negocio del realtor, respetando EXACTAMENTE su longitud, su estructura y su ritmo. Lo único que cambias son las palabras.

{profile_section}

════════════════════════════════════════
LA REGLA DE ORO: ADAPTACIÓN 1:1, NO REESCRITURA
════════════════════════════════════════
- MISMA LONGITUD. Tu guión adaptado (hook + desarrollo + conclusión juntos) debe tener prácticamente el mismo número de palabras y de frases que la transcripción original. Si el original tiene 9 frases, el tuyo tiene 9. Ni una más, ni una menos.
- MISMA ESTRUCTURA Y MISMO ORDEN. Frase por frase: la frase 1 del original es tu frase 1, la 2 tu 2, y así hasta el final. Mismo ritmo, mismas pausas, mismo tipo de frase (una pregunta se adapta como pregunta, una exclamación como exclamación).
- SOLO CAMBIAS LAS PALABRAS. Sustituye el tema del original por su equivalente en el mundo inmobiliario del realtor ({spec_desc}, en {market}), manteniendo la misma función de cada frase. Ejemplo: si el original dice "cuando compres un coche, mira bien el motor", tú dices con la misma forma "cuando compres un piso, mira bien las cuotas".
- Aplica el TONO y el ESTILO del realtor, pero SIN añadir longitud. Adaptar no es florecer.

❌ PROHIBIDO (esto es lo más importante):
- NO alargues ni extiendas ninguna parte, y MUY especialmente el desarrollo. El desarrollo es SOLO la parte central del original re-vestida, con su misma longitud. Prohibido añadir ejemplos, datos, cifras, anécdotas o frases que no estén en el original.
- NO resumas ni acortes.
- NO inventes contenido nuevo: si algo no está en el original, no está en tu adaptación.
- NO cambies el número de frases ni el orden de las ideas.

════════════════════════════════════════
LEGIBILIDAD (formato, no contenido)
════════════════════════════════════════
Las transcripciones automáticas llegan a menudo sin puntuación y todo seguido. Tu guión SÍ tiene que estar bien escrito y ser fácil de leer a cámara: puntúa las frases con normalidad (mayúsculas, comas, puntos, interrogaciones).

Esto NO es opcional y NO depende del original: aunque la transcripción venga entera en minúsculas y sin un solo signo de puntuación, tu guión SÍ va puntuado, con su mayúscula inicial en cada frase y su punto final. La regla de "copiar la estructura" se refiere al contenido y al orden, nunca a copiar la falta de puntuación.

Si el vídeo original es una ENUMERACIÓN o una lista de pares (por ejemplo "hábito → clase media / hábito → millonario", "error 1, error 2, error 3", "esto sí / esto no"), respeta ese formato de lista y escribe CADA elemento en su propia línea, separados por saltos de línea, conservando el mismo número de elementos y su orden.

Ojo: esto es solo FORMATO. No añade ni quita contenido, no alarga nada. Sigue aplicándose todo lo de arriba.

════════════════════════════════════════
CÓMO REPARTIR EN SECCIONES
════════════════════════════════════════
Divide tu adaptación (que ya tiene la misma longitud que el original) en las tres partes habladas, respetando dónde el original cambia de fase:
- hook: el arranque del original (gancho + promesa iniciales), re-vestido. Misma longitud que el arranque original.
- desarrollo: la parte central del original, re-vestida. MISMA longitud que la parte central original — no la extiendas.
- conclusion: el cierre / llamada a la acción del original, re-vestido.
Unidas, las tres partes deben leerse como la transcripción original pero en el mundo del realtor, y sumar la misma longitud.

Aparte, genera un "caption" corto para el post (esto sí es nuevo; no forma parte de la transcripción hablada).

════════════════════════════════════════
FORMATO DE RESPUESTA (JSON estricto, sin texto adicional)
════════════════════════════════════════

{{
  "estructura_detectada": "1 línea: de qué va el vídeo original y a qué tema inmobiliario lo has adaptado",
  "hook": "El arranque del original, adaptado (misma longitud)",
  "desarrollo": "La parte central del original, adaptada — MISMA longitud, sin extender",
  "conclusion": "El cierre/CTA del original, adaptado",
  "caption": "Caption corto con emojis y hashtags inmobiliarios en español"
}}"""


def generate_script(
    transcript: str,
    user: User,
    profile: Optional[RealtorProfile],
    custom_instructions: str = "",
) -> dict:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    instructions_block = ""
    if custom_instructions.strip():
        instructions_block = f"""
INSTRUCCIONES ESPECÍFICAS DEL REALTOR:
{custom_instructions.strip()}

Ten en cuenta estas instrucciones al adaptar el guión.
"""

    palabras = len(transcript.split())
    user_message = f"""Transcripción del vídeo original ({palabras} palabras):

---
{transcript}
---
{instructions_block}
Adapta esta transcripción palabra por palabra al perfil del realtor: mismo número de frases, mismo orden y misma longitud (aproximadamente {palabras} palabras en total entre hook + desarrollo + conclusión, margen máximo ±10%). Solo cambias las palabras para llevar el tema a su mundo inmobiliario; no alargues, no resumas, no inventes. Devuelve únicamente el JSON indicado."""

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4000,
        system=_build_system_prompt(profile, user),
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()

    json_start = raw.find("{")
    json_end = raw.rfind("}") + 1
    if json_start == -1 or json_end == 0:
        raise ValueError("La respuesta de Claude no contiene JSON válido.")

    parsed = json.loads(raw[json_start:json_end])

    required_keys = {"hook", "desarrollo", "conclusion", "caption"}
    if not required_keys.issubset(parsed.keys()):
        raise ValueError(f"Faltan campos en la respuesta: {required_keys - parsed.keys()}")

    return parsed
