from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Script, RealtorProfile
from app.auth import require_admin, hash_password
from app.services.profile_extractor import extract_profile_from_transcript

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def _active_profile(user: User, db: Session) -> RealtorProfile:
    """Devuelve el perfil activo del usuario (lo crea si no tiene ninguno)."""
    prof = next((p for p in user.profiles if p.is_active), None)
    if prof is None and user.profiles:
        prof = user.profiles[0]
    if prof is None:
        prof = RealtorProfile(user_id=user.id, profile_name="Mi Perfil", is_active=True)
        db.add(prof)
        db.commit()
        db.refresh(user)
        prof = user.profiles[0]
    return prof


def _user_stats(user: User, db: Session) -> dict:
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    scripts_month = db.query(Script).filter(Script.user_id == user.id, Script.created_at >= month_start).count()
    scripts_total = db.query(Script).filter(Script.user_id == user.id).count()
    return {"scripts_month": scripts_month, "scripts_total": scripts_total}


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    today_start = datetime(now.year, now.month, now.day)

    total_scripts_month = db.query(Script).filter(Script.created_at >= month_start).count()
    total_scripts_today = db.query(Script).filter(Script.created_at >= today_start).count()
    total_scripts_all = db.query(Script).count()
    total_users = db.query(User).filter(User.is_admin == False).count()
    active_users = db.query(User).filter(User.is_admin == False, User.is_active == True).count()

    # Top 5 realtors este mes
    all_realtors = db.query(User).filter(User.is_admin == False).all()
    top_realtors = sorted(
        [{"user": u, **_user_stats(u, db)} for u in all_realtors],
        key=lambda x: x["scripts_month"],
        reverse=True,
    )[:5]

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "user": current_user,
            "total_scripts_month": total_scripts_month,
            "total_scripts_today": total_scripts_today,
            "total_scripts_all": total_scripts_all,
            "total_users": total_users,
            "active_users": active_users,
            "top_realtors": top_realtors,
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def list_users(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    realtors = db.query(User).filter(User.is_admin == False).order_by(User.created_at.desc()).all()
    realtors_data = [{"user": u, **_user_stats(u, db)} for u in realtors]
    return templates.TemplateResponse(
        "admin/users.html",
        {"request": request, "user": current_user, "realtors": realtors_data},
    )


@router.get("/users/new", response_class=HTMLResponse)
async def new_user_page(request: Request, current_user: User = Depends(require_admin)):
    return templates.TemplateResponse(
        "admin/user_form.html",
        {"request": request, "user": current_user, "edit_user": None, "error": None},
    )


@router.post("/users/new")
async def create_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    monthly_limit: str = Form(""),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            "admin/user_form.html",
            {"request": request, "user": current_user, "edit_user": None, "error": "Ya existe un usuario con ese email."},
            status_code=400,
        )

    limit = int(monthly_limit) if monthly_limit.strip() else None
    new_user = User(
        email=email,
        password_hash=hash_password(password),
        name=name.strip(),
        is_admin=False,
        is_active=True,
        monthly_limit=limit,
        must_change_password=True,
        temp_password=password,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    # Tras crear, vamos a su ficha para configurar el perfil (onboarding)
    return RedirectResponse(url=f"/admin/users/{new_user.id}", status_code=303)


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    user_id: int,
    request: Request,
    saved: str = "",
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    realtor = db.query(User).filter(User.id == user_id).first()
    if not realtor:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    profile = _active_profile(realtor, db)
    scripts = (
        db.query(Script)
        .filter(Script.user_id == user_id)
        .order_by(Script.created_at.desc())
        .limit(20)
        .all()
    )
    stats = _user_stats(realtor, db)
    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "user": current_user,
            "realtor": realtor,
            "profile": profile,
            "scripts": scripts,
            "saved": saved,
            **stats,
        },
    )


@router.post("/users/{user_id}/edit")
async def edit_user(
    user_id: int,
    request: Request,
    name: str = Form(...),
    monthly_limit: str = Form(""),
    is_active: str = Form("off"),
    new_password: str = Form(""),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    realtor = db.query(User).filter(User.id == user_id).first()
    if not realtor:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    realtor.name = name.strip()
    realtor.monthly_limit = int(monthly_limit) if monthly_limit.strip() else None
    realtor.is_active = is_active == "on"
    if new_password.strip():
        realtor.password_hash = hash_password(new_password.strip())
        realtor.temp_password = new_password.strip()
        realtor.must_change_password = True

    db.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)


# ── Guardar el perfil del realtor (solo admin) ────────────────────────────
@router.post("/users/{user_id}/profile")
async def save_user_profile(
    user_id: int,
    display_name: str = Form(""),
    market: str = Form(""),
    tone: str = Form("cercano"),
    specialization: str = Form("todo_tipo"),
    speaking_notes: str = Form(""),
    about_me: str = Form(""),
    cliente_ideal: str = Form(""),
    objeciones: str = Form(""),
    casos_exito: str = Form(""),
    objetivo_cta: str = Form(""),
    temas_evitar: str = Form(""),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    realtor = db.query(User).filter(User.id == user_id).first()
    if not realtor:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    p = _active_profile(realtor, db)
    p.display_name   = display_name.strip() or None
    p.market         = market.strip() or None
    p.tone           = tone
    p.specialization = specialization
    p.speaking_notes = speaking_notes.strip() or None
    p.about_me       = about_me.strip() or None
    p.cliente_ideal  = cliente_ideal.strip() or None
    p.objeciones     = objeciones.strip() or None
    p.casos_exito    = casos_exito.strip() or None
    p.objetivo_cta   = objetivo_cta.strip() or None
    p.temas_evitar   = temas_evitar.strip() or None
    db.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}?saved=profile", status_code=303)


# ── Autorrellenar perfil desde la transcripción (solo admin) ──────────────
@router.post("/extract-profile")
async def admin_extract_profile(
    transcript: str = Form(""),
    current_user: User = Depends(require_admin),  # solo admin (la llamada consume API)
):
    """Analiza la transcripción de la llamada con IA y devuelve los campos del perfil (sin guardar)."""
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Pega la transcripción de la llamada primero.")
    try:
        fields = extract_profile_from_transcript(transcript)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al analizar la transcripción: {str(e)}")
    return JSONResponse(fields)
