from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from app.models import User
from app.auth import get_current_user
from app.services.robert_chat import preguntar

router = APIRouter()


class Mensaje(BaseModel):
    role: Literal["alumno", "robert"]
    content: str


class PreguntaRequest(BaseModel):
    pregunta: str
    historial: List[Mensaje] = []


@router.post("/robert/ask")
async def robert_ask(
    payload: PreguntaRequest,
    current_user: User = Depends(get_current_user),
):
    pregunta = payload.pregunta.strip()
    if not pregunta:
        raise HTTPException(status_code=422, detail="Escribe una pregunta.")

    historial = [{"role": m.role, "content": m.content} for m in payload.historial]

    try:
        respuesta = preguntar(historial=historial, pregunta=pregunta)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al responder: {str(e)}")

    return JSONResponse({"respuesta": respuesta})
