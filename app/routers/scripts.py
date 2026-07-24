from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Script
from app.auth import get_current_user, hash_password
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
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    used = _scripts_this_month(current_user, db)
    remaining = None
    if current_user.monthly_limit is not None:
        remaining = max(0, current_user.monthly_limit - used)

    recent_scripts = (
        db.query(Script)
        .filter(Script.user_id == current_user.id)
        .order_by(Script.created_at.desc())
        .limit(5)
        .all()
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "used": used,
            "remaining": remaining,
            "limit": current_user.monthly_limit,
            "recent_scripts": recent_scripts,
            # El popup de cambiar contraseña NO debe salir si es el admin impersonando;
            # solo cuando entra el realtor real. El flag en BD no se toca.
            "must_change_password": current_user.must_change_password
            and not getattr(current_user, "impersonated", False),
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
    # Al impersonar (admin probando el perfil del realtor) no aplicamos el límite mensual
    impersonando = getattr(current_user, "impersonated", False)
    if current_user.monthly_limit is not None and not impersonando:
        used = _scripts_this_month(current_user, db)
        if used >= current_user.monthly_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Has alcanzado tu límite de {current_user.monthly_limit} guiones este mes. Contacta con el administrador.",
            )

    try:
        result_trans = get_transcript(payload.url.strip())
        transcript = result_trans["transcript"]
        thumbnail_path = result_trans["thumbnail_path"]
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener la transcripción: {str(e)}")

    try:
        result = generate_script(
            transcript=transcript,
            user=current_user,
            profile=current_user.profile,
            custom_instructions=payload.custom_instructions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al generar el guión: {str(e)}")

    estructura = result.get("estructura_detectada") or None

    script = Script(
        user_id=current_user.id,
        source_url=payload.url.strip(),
        original_transcript=transcript,
        hook=result["hook"],
        development=result["desarrollo"],
        conclusion=result["conclusion"],
        caption=result["caption"],
        custom_instructions=payload.custom_instructions.strip() or None,
        thumbnail_path=thumbnail_path,
        estructura_detectada=estructura,
    )
    db.add(script)
    db.commit()
    db.refresh(script)

    used_now = _scripts_this_month(current_user, db)
    remaining = None
    if current_user.monthly_limit is not None:
        remaining = max(0, current_user.monthly_limit - used_now)

    return JSONResponse({
        "hook": result["hook"],
        "desarrollo": result["desarrollo"],
        "conclusion": result["conclusion"],
        "caption": result["caption"],
        "estructura_detectada": estructura,
        "script_id": script.id,
        "thumbnail_path": thumbnail_path,
        "used": used_now,
        "remaining": remaining,
        "limit": current_user.monthly_limit,
    })


class ChangePasswordRequest(BaseModel):
    new_password: str
    confirm_password: str


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=422, detail="La contraseña debe tener al menos 8 caracteres.")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Las contraseñas no coinciden.")

    current_user.password_hash = hash_password(payload.new_password)
    current_user.must_change_password = False
    current_user.temp_password = None
    db.commit()
    return JSONResponse({"ok": True})


@router.get("/history", response_class=HTMLResponse)
async def history(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
