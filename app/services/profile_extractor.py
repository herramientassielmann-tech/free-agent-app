import json
import anthropic
from app.config import ANTHROPIC_API_KEY

# Valores válidos de los enums del perfil (deben coincidir con app/models.py)
VALID_TONES = {"formal", "cercano", "energetico", "inspiracional"}
VALID_SPECIALIZATIONS = {
    "primera_vivienda", "lujo", "inversion", "comercial", "todo_tipo",
}

# Campos de texto libre que devuelve el extractor
TEXT_FIELDS = [
    "display_name", "market", "speaking_notes", "about_me",
    "cliente_ideal", "objeciones", "casos_exito", "objetivo_cta", "temas_evitar",
]

_SYSTEM_PROMPT = """Eres un analista de Free Agent Academy, una academia que forma a agentes inmobiliarios (realtors) para crear contenido en redes y vender. Tu tarea es leer la TRANSCRIPCIÓN de una llamada de onboarding con un alumno y extraer, de forma estructurada, su perfil para configurar la herramienta que le genera guiones de vídeo.

REGLAS:
- Trabaja SOLO con lo que dice la transcripción. NO inventes datos que no aparezcan.
- Si un campo no se menciona ni se puede deducir con seguridad, déjalo como cadena vacía "" (para los campos de texto). No rellenes con suposiciones.
- Redacta cada campo de texto en tercera persona o en forma descriptiva breve, listo para usarse como contexto de un generador de guiones (no copies el diálogo literal, sintetiza).
- Escribe todo en español.

CAMPOS A EXTRAER:
- display_name: el nombre con el que el alumno se presenta / quiere aparecer en cámara.
- market: su ciudad y, si los dice, los barrios o zonas CONCRETAS donde trabaja (ej. "Miami, sobre todo Brickell y Coral Gables"). La especificidad importa.
- tone: SOLO uno de estos valores exactos, el que mejor describa cómo habla: "cercano" (natural, de tú a tú), "formal" (profesional, técnico), "energetico" (dinámico, mucho ritmo), "inspiracional" (motivador, enfocado en sueños/cambio de vida). Si no está claro, usa "cercano".
- specialization: SOLO uno de estos valores exactos: "primera_vivienda", "lujo", "inversion", "comercial", "todo_tipo". Elige el que mejor encaje con a qué se dedica o quiere dedicarse. Si no está claro, usa "todo_tipo".
- speaking_notes: cómo habla — muletillas, expresiones propias, cómo arranca sus vídeos, si usa humor, si tutea, su ritmo. Recoge frases textuales suyas si las dice.
- about_me: su historia y autoridad — años de experiencia, hitos, su "porqué", y qué le diferencia del resto de agentes de su zona.
- cliente_ideal: a quién le habla / su cliente objetivo (ej. "compradores primerizos", "inversores extranjeros", "familias que se mudan").
- objeciones: los miedos, dudas y objeciones que más le repiten sus clientes (materia prima para los hooks).
- casos_exito: logros, cifras o ventas concretas de las que esté orgulloso (prueba social).
- objetivo_cta: qué quiere conseguir con el contenido y qué llamada a la acción prefiere (ej. "que le escriban al DM", "conseguir seguidores", "que comenten una palabra", "agendar llamadas").
- temas_evitar: temas que NO quiere tocar, o cosas sensibles/legales que debe evitar decir. Vacío si no lo menciona.

FORMATO DE RESPUESTA (JSON estricto, sin texto adicional):
{
  "display_name": "",
  "market": "",
  "tone": "cercano",
  "specialization": "todo_tipo",
  "speaking_notes": "",
  "about_me": "",
  "cliente_ideal": "",
  "objeciones": "",
  "casos_exito": "",
  "objetivo_cta": "",
  "temas_evitar": ""
}"""


def extract_profile_from_transcript(transcript: str) -> dict:
    """Analiza la transcripción de la llamada de onboarding y devuelve los campos del perfil."""
    transcript = (transcript or "").strip()
    if not transcript:
        raise ValueError("La transcripción está vacía.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""Transcripción de la llamada de onboarding:

---
{transcript}
---

Extrae el perfil del alumno en el formato JSON indicado."""

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=3000,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = message.content[0].text.strip()
    json_start = raw.find("{")
    json_end = raw.rfind("}") + 1
    if json_start == -1 or json_end == 0:
        raise ValueError("La respuesta del análisis no contiene JSON válido.")

    parsed = json.loads(raw[json_start:json_end])

    # Normalizar: enums válidos y campos de texto siempre presentes como str
    tone = str(parsed.get("tone", "")).strip().lower()
    result = {"tone": tone if tone in VALID_TONES else "cercano"}

    spec = str(parsed.get("specialization", "")).strip().lower()
    result["specialization"] = spec if spec in VALID_SPECIALIZATIONS else "todo_tipo"

    for field in TEXT_FIELDS:
        value = parsed.get(field, "")
        result[field] = str(value).strip() if value is not None else ""

    return result
