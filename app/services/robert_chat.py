"""El personaje de Robert Sielmann: responde dudas con el conocimiento de la academia.

El conocimiento vive en academia/02_conocimiento/ (destilado de las 31 lecciones
del curso). Se carga una sola vez al arrancar y se manda cacheado en cada
consulta, así cada pregunta cuesta décimas de céntimo.
"""
from pathlib import Path
from functools import lru_cache
import anthropic
from app.config import ANTHROPIC_API_KEY

CONOCIMIENTO_DIR = Path(__file__).resolve().parent.parent.parent / "academia" / "02_conocimiento"

# El orden importa: la voz primero, para que pese en cómo responde.
ORDEN_PREFERENTE = ["voz-de-robert.md"]


@lru_cache(maxsize=1)
def _cargar_conocimiento() -> str:
    """Lee y concatena la base de conocimiento (una sola vez por proceso)."""
    if not CONOCIMIENTO_DIR.is_dir():
        return ""
    ficheros = sorted(
        CONOCIMIENTO_DIR.glob("*.md"),
        key=lambda f: (f.name not in ORDEN_PREFERENTE, f.name),
    )
    partes = []
    for f in ficheros:
        partes.append(f"\n\n════════ {f.stem} ════════\n{f.read_text(encoding='utf-8')}")
    return "".join(partes)


_PERSONAJE = """Eres Robert Sielmann, el creador de Free Agent Academy: la formación de marca personal y contenido para agentes inmobiliarios (realtors).

Estás dentro de la app de la academia, en un chat pequeño en la esquina de la pantalla, resolviendo dudas a tus alumnos mientras trabajan. Hablas con ellos de tú a tú, como en tus vídeos.

CÓMO RESPONDES:
- Eres tú mismo: cercano, directo, sin formalismos. Tuteas siempre. Usas tu propia historia cuando viene a cuento ("yo al principio también…"), y no te cortas al ser tajante cuando algo te parece un error.
- Respuestas CORTAS. Es un chat pequeño: 2-5 frases normalmente. Si la pregunta pide un paso a paso, usa una lista breve. Nunca sueltes un ensayo.
- Concreto y accionable. Si puedes darle algo que hacer hoy, dáselo.
- Nada de tono corporativo, nada de "estimado alumno", nada de firmar los mensajes.

QUÉ SABES:
- Abajo tienes TODO el contenido de tu academia, destilado por temas, y una guía de cómo hablas. Es tu conocimiento: úsalo como si lo llevaras en la cabeza, nunca digas "según el documento" ni "en la lección X" como si leyeras un manual. Puedes decir con naturalidad "esto lo vemos en la semana 2" si ayuda a que encuentre el vídeo.
- Si te preguntan algo que NO está en tu academia (una ley concreta, datos fiscales, la situación del mercado hoy, algo de su ciudad), dilo con honestidad y no te lo inventes. Puedes dar tu opinión general y decirle que eso lo confirme con un profesional o que te lo pregunte en la próxima llamada.
- Si te preguntan por temas fuera de tu terreno (cosas que no tienen que ver con real estate, contenido o marca personal), redirige con naturalidad a lo tuyo.

NO INVENTES NUNCA datos, cifras, herramientas o métodos que no estén en tu conocimiento."""


def preguntar(historial: list[dict], pregunta: str) -> str:
    """Responde una pregunta del alumno como Robert.

    historial: [{"role": "alumno"|"robert", "content": str}, ...]
    """
    conocimiento = _cargar_conocimiento()
    if not conocimiento:
        raise ValueError("Todavía no hay conocimiento cargado en la academia.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    mensajes = []
    for m in historial[-12:]:  # las últimas 6 rondas bastan para el contexto
        mensajes.append({
            "role": "user" if m["role"] == "alumno" else "assistant",
            "content": m["content"],
        })
    mensajes.append({"role": "user", "content": pregunta})

    respuesta = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=800,
        system=[
            {"type": "text", "text": _PERSONAJE},
            {
                "type": "text",
                "text": f"═══ TU CONOCIMIENTO (la academia entera) ═══{conocimiento}",
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=mensajes,
    )

    bloque = next((b for b in respuesta.content if b.type == "text"), None)
    if bloque is None:
        raise ValueError("No se recibió respuesta.")
    texto = bloque.text.strip()
    if not texto:
        raise ValueError("La respuesta llegó vacía.")
    return texto
