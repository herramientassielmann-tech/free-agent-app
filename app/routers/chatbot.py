from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, LeadConversation, LeadMessage
from app.auth import get_current_user
from app.services.lead_chat import suggest_reply

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _own_conversation(cid: int, user: User, db: Session) -> LeadConversation:
    conv = db.query(LeadConversation).filter(
        LeadConversation.id == cid, LeadConversation.user_id == user.id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada.")
    return conv


@router.get("/chatbot", response_class=HTMLResponse)
async def chatbot_list(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversations = (
        db.query(LeadConversation)
        .filter(LeadConversation.user_id == current_user.id)
        .order_by(LeadConversation.updated_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "chatbot_list.html",
        {"request": request, "user": current_user, "conversations": conversations},
    )


@router.post("/chatbot/new")
async def chatbot_new(
    lead_name: str = Form(...),
    lead_context: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = LeadConversation(
        user_id=current_user.id,
        lead_name=lead_name.strip() or "Lead sin nombre",
        lead_context=lead_context.strip() or None,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return RedirectResponse(url=f"/chatbot/{conv.id}", status_code=303)


@router.get("/chatbot/{cid}", response_class=HTMLResponse)
async def chatbot_thread(
    cid: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _own_conversation(cid, current_user, db)
    return templates.TemplateResponse(
        "chatbot_thread.html",
        {"request": request, "user": current_user, "conv": conv},
    )


@router.post("/chatbot/{cid}/send")
async def chatbot_send(
    cid: int,
    client_message: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _own_conversation(cid, current_user, db)
    client_message = client_message.strip()
    if not client_message:
        raise HTTPException(status_code=422, detail="Pega lo que ha dicho el cliente primero.")

    history = [{"role": m.role, "content": m.content} for m in conv.messages]

    try:
        respuesta = suggest_reply(
            lead_context=conv.lead_context or "",
            history=history,
            client_message=client_message,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar la sugerencia: {str(e)}")

    db.add(LeadMessage(conversation_id=conv.id, role="cliente", content=client_message))
    sugerencia = LeadMessage(conversation_id=conv.id, role="sugerencia", content=respuesta)
    db.add(sugerencia)
    conv.updated_at = datetime.utcnow()  # onupdate no dispara solo por añadir mensajes hijos
    db.commit()
    db.refresh(sugerencia)

    return JSONResponse({
        "respuesta": respuesta,
        "created_at": sugerencia.created_at.strftime("%H:%M"),
    })


@router.post("/chatbot/{cid}/context")
async def chatbot_update_context(
    cid: int,
    lead_context: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _own_conversation(cid, current_user, db)
    conv.lead_context = lead_context.strip() or None
    db.commit()
    return RedirectResponse(url=f"/chatbot/{cid}", status_code=303)


@router.post("/chatbot/{cid}/delete")
async def chatbot_delete(
    cid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = _own_conversation(cid, current_user, db)
    db.delete(conv)
    db.commit()
    return RedirectResponse(url="/chatbot", status_code=303)
