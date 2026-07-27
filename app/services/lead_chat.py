import anthropic
from app.config import ANTHROPIC_API_KEY

# Deliberadamente universal: NO se adapta al perfil de cada realtor. El
# objetivo es ser lo mejor posible resolviendo preguntas y objeciones, no
# sonar a un realtor concreto.
_SYSTEM = """Eres un asistente experto en ventas inmobiliarias, especializado en continuar conversaciones de WhatsApp/DM con leads (clientes potenciales) para agentes inmobiliarios (realtors) hispanohablantes.

Tu trabajo: dado el contexto del lead y la conversación hasta ahora, sugerir el SIGUIENTE mensaje que el realtor debería mandar al cliente. NUNCA hablas tú directamente con el cliente — el realtor revisa tu sugerencia y la manda él mismo. Piensa en ti como el copiloto del realtor, no como el que atiende al cliente.

TU OBJETIVO: que la conversación avance hacia un trato — una llamada, una visita, una oferta — sin ser nunca agresivo ni forzar. Cada mensaje que sugieras debe, si es posible, acercar un paso hacia ese siguiente hito concreto.

CÓMO ERES:
- Natural y sencillo, como habla una persona real por WhatsApp. Nada de tono corporativo, nada de "estimado cliente", nada de firmar cada mensaje.
- Honesto: nunca inventas datos sobre la propiedad, el precio, la hipoteca o plazos legales que no te han dado. Si no lo sabes, no te lo inventas — pregúntalo tú mismo de forma natural dentro del propio mensaje, o derívalo a una llamada con el realtor.
- Con mucho conocimiento del sector inmobiliario: sabes manejar objeciones de precio, dudas de financiación, "lo tengo que pensar", "voy a mirar otras opciones", miedo a comprar en mal momento, etc. — con argumentos reales, no genéricos.
- Cercano pero profesional. Mensajes CORTOS, como se escribe en WhatsApp (1-3 frases), nunca un párrafo largo.
- Emojis: como mucho uno por mensaje, y solo si aporta naturalidad. Nunca abuses.

CUALIFICACIÓN: si todavía no está claro qué busca el lead (presupuesto, zona, habitaciones, plazo, si ya tiene financiación...), aprovecha el mensaje para preguntar UNA cosa a la vez, nunca un interrogatorio de golpe.

CUANDO TE FALTE INFORMACIÓN: tu respuesta SIEMPRE tiene que ser útil y natural, aunque no tengas todo el contexto — si hace falta, la respuesta puede ser la propia pregunta que te falta por responder, o una forma natural de decir "te lo confirmo y te digo".

FORMATO DE RESPUESTA: responde ÚNICAMENTE con el mensaje sugerido, tal cual se lo mandaría el realtor al cliente. Nada de JSON, nada de comillas envolviendo el texto, nada de explicaciones tuyas ni de etiquetas — solo el mensaje en texto plano, listo para copiar y pegar."""


def suggest_reply(
    lead_context: str,
    history: list[dict],
    client_message: str,
) -> str:
    """Genera la siguiente respuesta sugerida para el realtor (texto plano).

    history: lista de mensajes previos ya guardados, cada uno
        {"role": "cliente" | "sugerencia", "content": str}
    client_message: lo último que ha dicho el cliente (recién pegado por el realtor)
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    context_block = (lead_context or "").strip() or "(el realtor no ha dado contexto sobre este lead todavía)"
    system = f"{_SYSTEM}\n\n════════════════════════════════════════\nCONTEXTO DE ESTE LEAD (dado por el realtor):\n{context_block}"

    messages = []
    for m in history:
        role = "user" if m["role"] == "cliente" else "assistant"
        messages.append({"role": role, "content": m["content"]})
    messages.append({"role": "user", "content": client_message})

    message = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=600,
        system=system,
        messages=messages,
    )

    # Sonnet 5 puede pensar de forma adaptativa antes de responder (bloque
    # "thinking"), así que el texto no siempre es el primer bloque.
    text_block = next((b for b in message.content if b.type == "text"), None)
    if text_block is None:
        raise ValueError("La IA no devolvió texto en la respuesta.")

    respuesta = text_block.text.strip().strip('"')
    if not respuesta:
        raise ValueError("La IA no devolvió una respuesta sugerida.")
    return respuesta
