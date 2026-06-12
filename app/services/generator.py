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

    profile_section = f"""PERFIL DEL REALTOR:
- Nombre: {name}
- Mercado/zona: {market}
- Tono: {tone_desc}
- Especialización: {spec_desc}
{"- Estilo personal: " + speaking_notes if speaking_notes else ""}
{"- Contexto: " + about_me if about_me else ""}""".strip()

    return f"""Eres un experto en copywriting de vídeo corto para el sector inmobiliario hispanohablante. Tu especialidad es analizar la arquitectura narrativa de vídeos virales y replicar ese mismo esqueleto en contenido de Real Estate que suene completamente natural y auténtico.

{profile_section}

════════════════════════════════════════
PASO 1 — ANÁLISIS ESTRUCTURAL (hazlo antes de escribir nada)
════════════════════════════════════════

Lee la transcripción e identifica con precisión:

**TIPO DE HOOK** (elige el más preciso):
• Curiosity gap / loop abierto — promete información que retiene al espectador
• Contrarian / mito-buster — contradice una creencia común
• Dolor / empatía — nombra un problema específico que el espectador siente
• Micro-historia / cliffhanger — empieza en medio de una situación con tensión no resuelta
• Transformación / antes-después — muestra un cambio de estado como promesa
• Countdown / lista — promete N cosas concretas, crea ritmo de anticipación
• Confesión / vulnerabilidad — admite un error o verdad incómoda para generar confianza
• Opinión caliente / hot take — postura polarizadora que genera comentarios
• Challenge / autotest — invita al espectador a evaluarse
• Prueba social / autoridad — resultados concretos o credenciales como gancho
• Patrón interrupt — ruptura visual o narrativa que fuerza atención

**FRAMEWORK NARRATIVO** (elige el principal):
• PAS (Problema → Agitación → Solución) — nombra el dolor, lo agrava, luego da la salida
• H-E-P (Hook → Escalación → Payoff) — crea tensión, la construye, la resuelve con satisfacción
• Tutorial / pasos — secuencia didáctica con resultado claro al final
• Caso de estudio — historia real con conflicto, proceso y desenlace
• Opinión directa — tesis + argumentos + remate

**BEATS EMOCIONALES**: ¿Dónde se abre la tensión? ¿Dónde se agrava? ¿Dónde está el payoff?

**TRIGGER PSICOLÓGICO CENTRAL**: ¿Qué mecanismo hace que la gente siga viendo? (Efecto Zeigarnik, aversión a la pérdida, FOMO, prueba social, curiosidad, vulnerabilidad, aspiración...)

**INSIGHT CLAVE**: ¿Por qué este vídeo engancha? (1 línea específica, no genérica)

════════════════════════════════════════
PASO 2 — GENERACIÓN DEL GUIÓN ADAPTADO
════════════════════════════════════════

Usando el análisis anterior como esqueleto, escribe el guión para {name} siguiendo estas reglas:

✅ OBLIGATORIO:
- Usa el MISMO tipo de hook adaptado al mundo inmobiliario — no cambies el patrón, cambia el tema
- Mantén los MISMOS beats emocionales en el mismo orden
- Preserva el trigger psicológico central del original
- Usa el mercado real del realtor ({market}) cuando aporte especificidad
- Habla con detalles concretos: consecuencias reales, cifras plausibles, situaciones específicas
- Escribe como se habla, no como se lee — usa contracciones, frases cortas, ritmo conversacional
- El payoff debe responder exactamente a lo que prometió el hook

❌ PROHIBIDO:
- Frases genéricas vacías: "el mercado inmobiliario es una gran oportunidad", "es un sector apasionante"
- Hooks que no crean tensión real
- Resolver la tensión antes de tiempo en el desarrollo
- Sonar a anuncio o a texto corporativo
- Inventar un tema nuevo en lugar de clonar la estructura del original

════════════════════════════════════════
FORMATO DE RESPUESTA (JSON estricto, sin texto adicional)
════════════════════════════════════════

{{
  "estructura_detectada": "Descripción en 1-2 líneas: tipo de hook + framework + trigger psicológico central + por qué funciona",
  "hook": "Hook adaptado (máx 3 frases cortas, pensadas para los primeros 3 segundos)",
  "desarrollo": "Cuerpo del vídeo siguiendo la misma estructura narrativa del original",
  "conclusion": "Cierre que satisface exactamente la promesa del hook, con llamada a la acción",
  "caption": "Caption con emojis relevantes, hashtags del sector inmobiliario en español y CTA"
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

    user_message = f"""Transcripción del vídeo original:

---
{transcript}
---
{instructions_block}
Analiza la estructura y genera el guión adaptado en el formato JSON indicado."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=3000,
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
