from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Script, RealtorProfile
from app.auth import require_admin, hash_password

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def _user_stats(user: User, db: Session) -> dict:
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
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
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

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
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/users/{user_id}", response_class=HTMLResponse)
async def user_detail(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    realtor = db.query(User).filter(User.id == user_id).first()
    if not realtor:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
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
            "scripts": scripts,
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

    db.commit()
    return RedirectResponse(url=f"/admin/users/{user_id}", status_code=303)
