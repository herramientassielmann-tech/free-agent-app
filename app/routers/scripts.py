from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Script
from app.auth import get_current_user
from app.services.transcription import get_transcript
from app.services.generator import generate_script

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _scripts_this_month(user: User, db: Session) -> int:
    now = datetime.utcnow()
    return (
        db.query(Script)
        .filter(
            Script.user_id == user.id,
            Script.created_at >= datetime(now.year, now.month, 1),
        )
        .count()
    )


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    used = _scripts_this_month(current_user, db)
    remaining = None
    if current_user.monthly_limit is not None:
        remaining = max(0, current_user.monthly_limit - used)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "used": used,
            "remaining": remaining,
            "limit": current_user.monthly_limit,
        },
    )


class GenerateRequest(BaseModel):
    url: str
    custom_instructions: str = ""


@router.post("/generate")
async def generate(
    payload: GenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Verificar límite mensual
    if current_user.monthly_limit is not None:
        used = _scripts_this_month(current_user, db)
        if used >= current_user.monthly_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Has alcanzado tu límite de {current_user.monthly_limit} guiones este mes. Contacta con el administrador para ampliar tu cuota.",
            )

    # Transcribir
    try:
        transcript = get_transcript(payload.url.strip())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener la transcripción: {str(e)}")

    # Generar guión
    try:
        result = generate_script(
            transcript=transcript,
            user=current_user,
            profile=current_user.profile,
            custom_instructions=payload.custom_instructions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar el guión: {str(e)}")

    # Guardar en DB
    script = Script(
        user_id=current_user.id,
        source_url=payload.url.strip(),
        original_transcript=transcript,
        hook=result["hook"],
        development=result["desarrollo"],
        conclusion=result["conclusion"],
        caption=result["caption"],
        custom_instructions=payload.custom_instructions.strip() or None,
    )
    db.add(script)
    db.commit()
    db.refresh(script)

    # Calcular cuota actualizada
    used_now = _scripts_this_month(current_user, db)
    remaining = None
    if current_user.monthly_limit is not None:
        remaining = max(0, current_user.monthly_limit - used_now)

    return JSONResponse({
        "hook": result["hook"],
        "desarrollo": result["desarrollo"],
        "conclusion": result["conclusion"],
        "caption": result["caption"],
        "script_id": script.id,
        "used": used_now,
        "remaining": remaining,
        "limit": current_user.monthly_limit,
    })


@router.get("/history", response_class=HTMLResponse)
async def history(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scripts = (
        db.query(Script)
        .filter(Script.user_id == current_user.id)
        .order_by(Script.created_at.desc())
        .limit(50)
        .all()
    )
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "user": current_user, "scripts": scripts},
    )
