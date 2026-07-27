from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, RealtorProfile
from app.auth import get_current_user
from app.services.ig_optimizer import optimize_ig_profile, ig_handle_from_link
from app.services.lead_questions import LEAD_QUESTIONS

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _own_profile(pid: int, user: User, db: Session) -> RealtorProfile:
    p = db.query(RealtorProfile).filter(
        RealtorProfile.id == pid,
        RealtorProfile.user_id == user.id,
    ).first()
    if not p:
        raise HTTPException(status_code=404)
    return p


def _ensure_profile_exists(user: User, db: Session):
    """Crea el perfil por defecto si el usuario no tiene ninguno."""
    if not user.profiles:
        p = RealtorProfile(user_id=user.id, profile_name="Mi Perfil", is_active=True)
        db.add(p)
        db.commit()
        db.refresh(user)


# ── Crear nuevo perfil ─────────────────────────────────────────────────
@router.post("/profile/new")
async def new_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.refresh(current_user)
    p = RealtorProfile(user_id=current_user.id, profile_name="Nuevo Perfil", is_active=False)
    db.add(p)
    db.commit()
    db.refresh(p)
    return RedirectResponse(url=f"/profile?pid={p.id}", status_code=303)


# ── Activar perfil ────────────────────────────────────────────────────
@router.post("/profile/{pid}/activate")
async def activate_profile(
    pid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.refresh(current_user)
    target = _own_profile(pid, current_user, db)
    for p in current_user.profiles:
        p.is_active = False
    target.is_active = True
    db.commit()
    return RedirectResponse(url=f"/profile?pid={pid}", status_code=303)


# ── Eliminar perfil ───────────────────────────────────────────────────
@router.post("/profile/{pid}/delete")
async def delete_profile(
    pid: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.refresh(current_user)
    if len(current_user.profiles) <= 1:
        return RedirectResponse(url=f"/profile?pid={pid}", status_code=303)
    target = _own_profile(pid, current_user, db)
    was_active = target.is_active
    db.delete(target)
    db.flush()
    db.refresh(current_user)
    if was_active and current_user.profiles:
        current_user.profiles[0].is_active = True
    db.commit()
    return RedirectResponse(url="/profile", status_code=303)


# ── Guardar perfil ────────────────────────────────────────────────────
@router.post("/profile/{pid}")
async def save_profile(
    pid: int,
    display_name: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """El alumno solo puede editar su nombre en cámara. El resto lo configura el admin."""
    p = _own_profile(pid, current_user, db)
    p.display_name = display_name.strip() or None
    db.commit()
    return RedirectResponse(url=f"/profile?pid={pid}&saved=1", status_code=303)


# ── Página de perfil ──────────────────────────────────────────────────
@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    pid: Optional[int] = None,
    saved: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.refresh(current_user)
    _ensure_profile_exists(current_user, db)
    db.refresh(current_user)

    profiles = current_user.profiles
    selected = next((p for p in profiles if p.id == pid), None) if pid else None
    if not selected:
        selected = current_user.profile or profiles[0]

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": current_user,
            "profiles": profiles,
            "selected": selected,
            "saved": bool(saved),
        },
    )


# ── Optimizar IG (self-service): siempre sobre el perfil propio ───────────
@router.get("/optimizar-ig", response_class=HTMLResponse)
async def optimizar_ig_self_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.refresh(current_user)
    _ensure_profile_exists(current_user, db)
    db.refresh(current_user)
    return templates.TemplateResponse(
        "optimizar_ig.html",
        {"request": request, "user": current_user, "profile": current_user.profile},
    )


@router.post("/optimizar-ig/generate")
async def optimizar_ig_self_generate(
    ig_link: str = Form(""),
    current_bio: str = Form(""),
    screenshot_data: str = Form(""),
    screenshot_media_type: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.refresh(current_user)
    profile = current_user.profile
    nombre = (profile.display_name if profile and profile.display_name else current_user.name) or "Realtor"
    handle = ig_handle_from_link(ig_link)
    try:
        opciones = optimize_ig_profile(
            nombre=nombre,
            profile=profile,
            current_bio=current_bio,
            current_handle=handle,
            screenshot_base64=screenshot_data or None,
            screenshot_media_type=screenshot_media_type or None,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al optimizar el perfil: {str(e)}")
    return JSONResponse({
        "opciones": opciones,
        "telefono": (profile.telefono if profile else None) or "",
    })


# ── Cualificar Leads: preguntas listas para copiar y enviar al cliente ────
@router.get("/cualificar-leads", response_class=HTMLResponse)
async def cualificar_leads_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "cualificar_leads.html",
        {"request": request, "user": current_user, "categorias": LEAD_QUESTIONS},
    )
