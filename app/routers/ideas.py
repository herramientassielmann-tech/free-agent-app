from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, StarterScript, StarterScriptCheck
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/ideas-iniciales", response_class=HTMLResponse)
async def ideas_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scripts = db.query(StarterScript).order_by(StarterScript.position).all()

    # Los guiones son comunes, pero el progreso es de cada realtor.
    checked_ids = {
        c.starter_script_id
        for c in db.query(StarterScriptCheck).filter(
            StarterScriptCheck.user_id == current_user.id
        ).all()
    }

    return templates.TemplateResponse(
        "ideas_iniciales.html",
        {
            "request": request,
            "user": current_user,
            "scripts": scripts,
            "checked_ids": checked_ids,
            "total": len(scripts),
            "hechos": len([s for s in scripts if s.id in checked_ids]),
        },
    )


@router.get("/ideas-iniciales/{sid}", response_class=HTMLResponse)
async def idea_detalle(
    sid: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vista grande de un guión, igual que la del generador."""
    script = db.query(StarterScript).filter(StarterScript.id == sid).first()
    if not script:
        raise HTTPException(status_code=404, detail="Guión no encontrado.")

    hecho = db.query(StarterScriptCheck).filter(
        StarterScriptCheck.user_id == current_user.id,
        StarterScriptCheck.starter_script_id == sid,
    ).first() is not None

    # Para poder pasar de una idea a la siguiente sin volver a la lista
    todos = db.query(StarterScript).order_by(StarterScript.position).all()
    idx = next((i for i, s in enumerate(todos) if s.id == sid), 0)

    return templates.TemplateResponse(
        "ideas_detalle.html",
        {
            "request": request,
            "user": current_user,
            "s": script,
            "hecho": hecho,
            "numero": idx + 1,
            "total": len(todos),
            "anterior": todos[idx - 1] if idx > 0 else None,
            "siguiente": todos[idx + 1] if idx < len(todos) - 1 else None,
        },
    )


@router.post("/ideas-iniciales/{sid}/toggle")
async def toggle_check(
    sid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marca/desmarca un guión como hecho. Solo afecta a este realtor."""
    script = db.query(StarterScript).filter(StarterScript.id == sid).first()
    if not script:
        raise HTTPException(status_code=404, detail="Guión no encontrado.")

    existing = db.query(StarterScriptCheck).filter(
        StarterScriptCheck.user_id == current_user.id,
        StarterScriptCheck.starter_script_id == sid,
    ).first()

    if existing:
        db.delete(existing)
        checked = False
    else:
        db.add(StarterScriptCheck(user_id=current_user.id, starter_script_id=sid))
        checked = True
    db.commit()

    hechos = db.query(StarterScriptCheck).filter(
        StarterScriptCheck.user_id == current_user.id
    ).count()
    total = db.query(StarterScript).count()

    return JSONResponse({"checked": checked, "hechos": hechos, "total": total})
