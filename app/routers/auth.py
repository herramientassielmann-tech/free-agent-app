from fastapi import APIRouter, Depends, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.auth import verify_password, create_access_token, get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Email o contraseña incorrectos."},
            status_code=401,
        )
    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Tu cuenta está desactivada. Contacta con el administrador."},
            status_code=403,
        )

    token = create_access_token({"sub": str(user.id), "is_admin": user.is_admin})
    redirect = RedirectResponse(url="/admin" if user.is_admin else "/", status_code=303)
    redirect.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=60 * 60 * 8,
        samesite="lax",
    )
    return redirect


@router.post("/logout")
@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response
