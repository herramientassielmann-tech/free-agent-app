from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, RealtorProfile
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": current_user, "profile": current_user.profile, "saved": False},
    )


@router.post("/profile")
async def save_profile(
    request: Request,
    display_name: str = Form(""),
    market: str = Form(""),
    tone: str = Form("cercano"),
    speaking_notes: str = Form(""),
    specialization: str = Form("todo_tipo"),
    about_me: str = Form(""),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(RealtorProfile).filter(RealtorProfile.user_id == current_user.id).first()
    if not profile:
        profile = RealtorProfile(user_id=current_user.id)
        db.add(profile)

    profile.display_name = display_name.strip() or None
    profile.market = market.strip() or None
    profile.tone = tone
    profile.speaking_notes = speaking_notes.strip() or None
    profile.specialization = specialization
    profile.about_me = about_me.strip() or None
    db.commit()
    db.refresh(current_user)

    return templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": current_user, "profile": profile, "saved": True},
    )
