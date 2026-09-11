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


def _registrar_acceso(user: User, request: Request, db: Session) -> None:
    """Deja constancia de que esta persona entró.

    No sirve para vigilar a nadie ni se enseña en ninguna pantalla. Para ganar
    una reclamación de cargo hacen falta tres cosas —contrato firmado, registro
    de IP y prueba de que accedió al producto— y esto es la tercera. Con pagos
    de 3.000 dólares y sin devoluciones, conviene tenerla.

    Nunca impide entrar: si falla el registro, la sesión sigue su curso.
    """
    try:
        from app.models import AccesoRegistrado
        reenviada = request.headers.get("x-forwarded-for", "")
        ip = (reenviada.split(",")[0].strip() if reenviada
              else (request.client.host if request.client else ""))
        db.add(AccesoRegistrado(
            user_id=user.id,
            ip=ip[:60] or None,
            user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        ))
        db.commit()
    except Exception:
        db.rollback()


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

    _registrar_acceso(user, request, db)

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
