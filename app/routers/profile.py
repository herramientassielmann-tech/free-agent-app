from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, RealtorProfile
from app.auth import get_current_user

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
    profile_name: str = Form("Mi Perfil"),
    display_name: str = Form(""),
    market: str = Form(""),
    tone: str = Form("cercano"),
    speaking_notes: str = Form(""),
    specialization: str = Form("todo_tipo"),
    about_me: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = _own_profile(pid, current_user, db)
    p.profile_name   = profile_name.strip() or "Mi Perfil"
    p.display_name   = display_name.strip() or None
    p.market         = market.strip() or None
    p.tone           = tone
    p.speaking_notes = speaking_notes.strip() or None
    p.specialization = specialization
    p.about_me       = about_me.strip() or None
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
