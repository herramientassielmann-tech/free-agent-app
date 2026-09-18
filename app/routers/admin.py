# Anotaciones diferidas: permite escribir `dict | None` y que el fichero
# siga siendo importable en Python 3.9, que es lo que hay en local para
# levantar los arneses de prueba. models.py ya lo hace.
from __future__ import annotations
from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import User, Script, RealtorProfile, ClipReunion
from app.auth import require_admin, hash_password, create_access_token, get_real_user, decode_token
from app.services.profile_extractor import extract_profile_from_transcript
from app.services.ig_optimizer import optimize_ig_profile, ig_handle_from_link

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


def _salud_descargas() -> dict | None:
    """Última revisión de las descargas, si el temporizador ya ha corrido.

    Lo escribe scripts/salud_descargas.py. Devuelve None si todavía no existe,
    para no dar una alarma falsa antes de la primera comprobación."""
    import json
    from pathlib import Path
    fichero = Path(__file__).resolve().parent.parent.parent / "estado_descargas.json"
    if not fichero.exists():
        return None
    try:
        datos = json.loads(fichero.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    # Una revisión vieja también es señal de alarma: significa que el
    # temporizador no está corriendo y nadie está vigilando.
    try:
        revisado = datetime.fromisoformat(datos["revisado"].rstrip("Z"))
        datos["horas"] = round((datetime.utcnow() - revisado).total_seconds() / 3600)
    except (KeyError, ValueError):
        datos["horas"] = None
    return datos


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
            "salud_descargas": _salud_descargas(),
            "clips_biblioteca": db.query(ClipReunion).count(),
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
    reiniciada: str = "",
    error: str = "",
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
            "reiniciada": reiniciada,
            "error": error,
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


@router.post("/users/{user_id}/reiniciar-password")
async def reiniciar_password(
    user_id: int,
    password: str = Form(""),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Le pone una contraseña temporal al realtor y le obliga a cambiarla.

    Existe aparte del formulario de editar porque son dos gestos distintos:
    editar es «corrijo un dato», esto es «ha perdido el acceso, se lo devuelvo
    ahora». Mezclarlos obligaba a reenviar nombre, límite y estado para tocar
    solo la contraseña.

    `temp_password` se guarda en claro a propósito: es la que hay que dictarle
    por WhatsApp, y deja de servir en cuanto él elige la suya —ahí se borra—.
    """
    realtor = db.query(User).filter(User.id == user_id).first()
    if not realtor:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # El aviso de «cambia tu contraseña» vive en el panel del realtor, y un
    # admin entra directo a /admin: nunca lo vería, y se quedaría con una
    # contraseña temporal para siempre sin saberlo.
    if realtor.is_admin:
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error=admin", status_code=303)

    limpia = password.strip()
    if len(limpia) < 8:
        return RedirectResponse(
            url=f"/admin/users/{user_id}?error=corta", status_code=303)

    realtor.password_hash = hash_password(limpia)
    realtor.temp_password = limpia
    realtor.must_change_password = True
    db.commit()
    return RedirectResponse(
        url=f"/admin/users/{user_id}?reiniciada=1", status_code=303)


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
    telefono: str = Form(""),
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
    p.telefono       = telefono.strip() or None
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


# ── Impersonar: entrar como un realtor desde la cuenta de admin ───────────
def _set_auth_cookie(resp: RedirectResponse, token: str):
    resp.set_cookie(
        key="access_token", value=token, httponly=True, max_age=60 * 60 * 8, samesite="lax"
    )


@router.post("/users/{user_id}/impersonate")
async def impersonate_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id, User.is_admin == False).first()
    if not target:
        raise HTTPException(status_code=404, detail="Realtor no encontrado.")
    token = create_access_token(
        {"sub": str(current_user.id), "is_admin": True, "imp": str(target.id)}
    )
    resp = RedirectResponse(url="/", status_code=303)
    _set_auth_cookie(resp, token)
    return resp


@router.post("/stop-impersonation")
async def stop_impersonation(
    real_user: User = Depends(get_real_user),
    access_token: Optional[str] = Cookie(default=None),
):
    payload = decode_token(access_token) if access_token else None
    imp_id = payload.get("imp") if payload else None
    if not real_user.is_admin or imp_id is None:
        return RedirectResponse(url="/", status_code=303)
    token = create_access_token({"sub": str(real_user.id), "is_admin": True})
    resp = RedirectResponse(url=f"/admin/users/{imp_id}", status_code=303)
    _set_auth_cookie(resp, token)
    return resp


# ── Optimizar IG: 3 versiones optimizadas del perfil de Instagram ─────────
@router.get("/optimizar-ig", response_class=HTMLResponse)
async def optimizar_ig_page(
    request: Request,
    uid: Optional[int] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    realtors = db.query(User).filter(User.is_admin == False).order_by(User.name).all()
    selected = None
    profile = None
    if uid:
        selected = db.query(User).filter(User.id == uid, User.is_admin == False).first()
        if selected:
            profile = _active_profile(selected, db)
    return templates.TemplateResponse(
        "admin/optimizar_ig.html",
        {
            "request": request,
            "user": current_user,
            "realtors": realtors,
            "selected": selected,
            "profile": profile,
        },
    )


@router.post("/optimizar-ig/generate")
async def optimizar_ig_generate(
    user_id: int = Form(...),
    ig_link: str = Form(""),
    current_bio: str = Form(""),
    screenshot_data: str = Form(""),
    screenshot_media_type: str = Form(""),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    realtor = db.query(User).filter(User.id == user_id, User.is_admin == False).first()
    if not realtor:
        raise HTTPException(status_code=404, detail="Realtor no encontrado.")
    profile = _active_profile(realtor, db)
    nombre = (profile.display_name if profile and profile.display_name else realtor.name) or "Realtor"
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


# ── Cualificar Leads: ahora es una sección general, ver /cualificar-leads ──
@router.get("/cualificar-leads")
async def cualificar_leads_redirect():
    return RedirectResponse(url="/cualificar-leads", status_code=301)


# ── Asesor (antes "Chatbot"): ahora es una sección general, ver /chatbot ──
@router.get("/chatbot")
async def asesor_list_redirect():
    return RedirectResponse(url="/chatbot", status_code=301)


@router.get("/chatbot/{cid}")
async def asesor_thread_redirect(cid: int):
    return RedirectResponse(url=f"/chatbot/{cid}", status_code=301)


# ── Altas de alumnos (onboarding) ────────────────────────────────────────────

PASOS_ALTA = [
    ("agendado", "Agendado", "programada_para"),
    ("email", "Email", "email_enviado_en"),
    ("pago", "Pago", "pagado_en"),
    ("firma", "Firma", "contrato_firmado_en"),
    ("cuenta", "Cuenta", "cuenta_creada_en"),
    ("skool", "Skool", "skool_abierto_en"),
    ("onboarding", "Onboarding", "onboarding_agendado_en"),
]


def _fila_alta(a: "Alta") -> dict:
    """Una fila del panel. Todo se deduce de la base de datos y nada se marca a
    mano: un checklist que se marca a mano se pudre en dos semanas."""
    pasos = []
    for clave, titulo, campo in PASOS_ALTA:
        valor = getattr(a, campo, None)
        pasos.append({"clave": clave, "titulo": titulo, "hecho": bool(valor),
                      "fecha": valor.strftime("%d/%m") if valor else None})

    # Cuánto lleva parado en el primer paso que le falta: se cuenta desde el
    # último que sí completó, que es cuando dejó de avanzar.
    dias = None
    if not a.completada:
        hechas = [getattr(a, c) for _, _, c in PASOS_ALTA if getattr(a, c, None)]
        desde = max(hechas) if hechas else a.created_at
        dias = (datetime.utcnow() - desde).days

    return {
        "alta": a, "pasos": pasos,
        "dias_atascado": dias,
        "completada": a.completada,
        "abiertos": a.accesos_abiertos,
    }


@router.get("/altas", response_class=HTMLResponse)
async def altas(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models import Alta
    filas = [_fila_alta(a) for a in
             db.query(Alta).order_by(Alta.created_at.desc()).all()]
    return templates.TemplateResponse("admin/altas.html", {
        "request": request, "user": current_user,
        "filas": filas, "columnas": [t for _, t, _ in PASOS_ALTA],
        "pendientes": sum(1 for f in filas if not f["completada"]),
    })


@router.post("/altas/nueva")
async def alta_nueva(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    nombre: str = Form(...),
    email: str = Form(...),
    cuando: str = Form(""),
):
    """Alta a mano. Es el camino cuando Calendly no manda avisos (plan gratuito)
    o cuando alguien cierra por fuera del embudo."""
    from app.models import Alta
    from app.routers.bienvenida import caducidad, nuevo_token
    programada = None
    if cuando:
        for formato in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                programada = datetime.strptime(cuando.strip(), formato)
                break
            except ValueError:
                continue
    a = Alta(
        nombre=nombre.strip()[:150], email=email.strip().lower()[:255],
        programada_para=programada or datetime.utcnow(),
        token=nuevo_token(), token_expira=caducidad(),
    )
    db.add(a)
    db.commit()
    return RedirectResponse(url="/admin/altas", status_code=303)


@router.post("/altas/{aid}/desbloquear")
async def alta_desbloquear(
    aid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models import Alta
    a = db.get(Alta, aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Alta no encontrada")
    a.desbloqueado_a_mano = not a.desbloqueado_a_mano
    db.commit()
    return RedirectResponse(url="/admin/altas", status_code=303)


@router.post("/altas/{aid}/pago-manual")
async def alta_pago_manual(
    aid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Para el 50/50 y las transferencias que no pasan por Stripe."""
    from app.models import Alta
    a = db.get(Alta, aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Alta no encontrada")
    if a.pagado_en:
        a.pagado_en = None
        a.metodo_pago = None
    else:
        a.pagado_en = datetime.utcnow()
        a.metodo_pago = "manual"
    db.commit()
    return RedirectResponse(url="/admin/altas", status_code=303)


@router.post("/altas/{aid}/reenviar")
async def alta_reenviar(
    aid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Vuelve a mandar el correo de bienvenida y renueva el enlace si caducó."""
    from app.models import Alta
    from app.routers.bienvenida import caducidad
    from app.services.bienvenida_email import mandar_bienvenida
    a = db.get(Alta, aid)
    if a is None:
        raise HTTPException(status_code=404, detail="Alta no encontrada")
    if a.token_expira < datetime.utcnow():
        a.token_expira = caducidad()
        db.commit()
    if mandar_bienvenida(a):
        a.email_enviado_en = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/admin/altas", status_code=303)


@router.get("/altas/{aid}/contrato", response_class=HTMLResponse)
async def alta_contrato(
    aid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """El contrato firmado, tal cual se congeló. No se vuelve a pintar."""
    from app.models import Alta
    a = db.get(Alta, aid)
    if a is None or a.firma is None:
        raise HTTPException(status_code=404, detail="No hay contrato firmado")
    return HTMLResponse(a.firma.html_firmado)


# ── Seguimiento semanal de alumnos ───────────────────────────────────────────

# Solo estos dos se piden y se guardan. Las columnas de publicados y trials
# siguen en la tabla con lo que se anotó en su día, pero ya no se tocan: nadie
# podía comprobarlas sin preguntar al alumno, así que costaban cada semana y
# valían poco.
CAMPOS_SEMANA = ("grabados", "editados")
SEMANAS_HISTORIAL = 8


def _lunes_de(d: "date") -> "date":
    """El lunes de la semana de esa fecha. Mismo criterio que el registro de
    tareas del CRM, para que las dos pantallas hablen de la misma semana."""
    return d - timedelta(days=d.weekday())


def _semana(db: Session, user_id: int, lunes: "date") -> "SemanaAlumno":
    """La fila de esa semana; se crea vacía la primera vez que se toca."""
    from app.models import SemanaAlumno
    fila = (db.query(SemanaAlumno)
              .filter(SemanaAlumno.user_id == user_id, SemanaAlumno.lunes == lunes)
              .first())
    if fila is None:
        fila = SemanaAlumno(user_id=user_id, lunes=lunes)
        db.add(fila)
        db.commit()
        db.refresh(fila)
    return fila


def _semana_json(s: "SemanaAlumno") -> dict:
    return {
        "grabados": s.grabados, "editados": s.editados,
        "sin_editar": s.sin_editar, "cumple": s.cumple,
        "nota": s.nota or "",
    }


@router.get("/alumnos", response_class=HTMLResponse)
async def alumnos(
    request: Request,
    semana: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models import SemanaAlumno
    hoy = datetime.utcnow().date()
    try:
        lunes = _lunes_de(datetime.strptime(semana, "%Y-%m-%d").date()) if semana else _lunes_de(hoy)
    except ValueError:
        lunes = _lunes_de(hoy)

    estudiantes = (db.query(User)
                     .filter(User.es_alumno.is_(True), User.is_active.is_(True))
                     .order_by(User.name)
                     .all())

    # El historial de las últimas semanas se trae de una vez: una consulta por
    # alumno y semana serían cincuenta viajes a la base de datos para pintar
    # una tabla.
    desde = lunes - timedelta(weeks=SEMANAS_HISTORIAL - 1)
    historico = {}
    for s in (db.query(SemanaAlumno)
                .filter(SemanaAlumno.lunes >= desde, SemanaAlumno.lunes <= lunes)
                .all()):
        historico[(s.user_id, s.lunes)] = s

    lunes_previos = [lunes - timedelta(weeks=i) for i in range(SEMANAS_HISTORIAL - 1, -1, -1)]
    filas = []
    for u in estudiantes:
        actual = historico.get((u.id, lunes))
        filas.append({
            "user": u,
            "datos": _semana_json(actual) if actual else {
                **{c: 0 for c in CAMPOS_SEMANA},
                "sin_editar": 0, "cumple": False, "nota": ""},
            "historial": [
                {"lunes": l.strftime("%d/%m"),
                 "editados": historico[(u.id, l)].editados if (u.id, l) in historico else 0,
                 "cumple": historico[(u.id, l)].cumple if (u.id, l) in historico else False,
                 # Sin fila no es «semana floja», es «no lo apuntamos». Pintar de
                 # rojo las semanas de antes de que entrara seria inventarse un
                 # incumplimiento que nunca ocurrio.
                 "hay_datos": (u.id, l) in historico}
                for l in lunes_previos
            ],
        })

    otras = (db.query(User)
               .filter(User.es_alumno.is_(False), User.is_admin.is_(False),
                       User.is_active.is_(True))
               .order_by(User.name).all())

    return templates.TemplateResponse("admin/alumnos.html", {
        "request": request, "user": current_user,
        "filas": filas, "lunes": lunes,
        "es_semana_actual": lunes == _lunes_de(hoy),
        "anterior": (lunes - timedelta(weeks=1)).isoformat(),
        "siguiente": (lunes + timedelta(weeks=1)).isoformat(),
        "cumplen": sum(1 for f in filas if f["datos"]["cumple"]),
        "minimo": 2,
        "otras_cuentas": otras,
    })


@router.post("/alumnos/{uid}/{lunes}")
async def alumno_marcar(
    uid: int,
    lunes: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    campo: str = Form(...),
    valor: str = Form(...),
):
    """Guarda una celda. Se llama a cada clic, sin recargar la página: si hay
    que pulsar 'guardar' después de cada número, el repaso del viernes deja de
    hacerse a la tercera semana."""
    if campo not in CAMPOS_SEMANA and campo != "nota":
        raise HTTPException(status_code=400, detail="Campo no válido")
    try:
        dia = datetime.strptime(lunes, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Semana no válida")

    alumno = db.get(User, uid)
    if alumno is None or alumno.is_admin:
        raise HTTPException(status_code=404, detail="Alumno no encontrado")

    fila = _semana(db, uid, _lunes_de(dia))
    if campo == "nota":
        fila.nota = (valor or "").strip()[:300] or None
    else:
        try:
            n = max(0, min(99, int(valor)))   # nadie graba 300 vídeos en una semana
        except ValueError:
            raise HTTPException(status_code=400, detail="Número no válido")
        setattr(fila, campo, n)
    fila.actualizado_en = datetime.utcnow()
    db.commit()
    db.refresh(fila)
    return JSONResponse(_semana_json(fila))


@router.post("/alumnos/{uid}/alta-seguimiento")
async def alumno_seguimiento(
    uid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Mete o saca a alguien del seguimiento. Las cuentas de prueba no son
    alumnos y si salieran en el panel lo volverían inservible."""
    u = db.get(User, uid)
    if u is None or u.is_admin:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada")
    u.es_alumno = not u.es_alumno
    db.commit()
    return RedirectResponse(url="/admin/alumnos", status_code=303)


# ── Tareas del equipo ────────────────────────────────────────────────────────

def _tarea_json(t: "TareaEquipo") -> dict:
    """La fila ya resuelta: la plantilla y el JS no hacen cuentas de fechas."""
    return {
        "id": t.id,
        "texto": t.texto,
        "asignado_a": t.asignado_a,
        "fecha_limite": t.fecha_limite.isoformat() if t.fecha_limite else None,
        "fecha_corta": t.fecha_limite.strftime("%d/%m") if t.fecha_limite else None,
        "prioridad": t.prioridad,
        "estado": t.estado,
        "vencida": t.vencida,
        "hoy": t.es_hoy,
        "notas": t.notas or "",
        "tiene_notas": bool((t.notas or "").strip()),
        "completada_en": t.completada_en.strftime("%d/%m") if t.completada_en else None,
    }


@router.get("/tareas", response_class=HTMLResponse)
async def tareas_equipo(
    request: Request,
    quien: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from collections import OrderedDict
    from app.models import TareaEquipo

    from app.services.tareas_texto import EQUIPO
    hoy = datetime.utcnow().date()

    consulta = db.query(TareaEquipo)
    # El filtro va por nombre: los tres entran con la misma cuenta, así que no
    # existe un "mías" que el servidor pueda deducir.
    elegido = next((n for n in EQUIPO if n.lower() == (quien or "").lower()), None)
    if elegido:
        consulta = consulta.filter(TareaEquipo.asignado_a == elegido)

    todas = consulta.order_by(
        # Sin fecha al final; dentro de cada día, lo urgente primero
        TareaEquipo.fecha_limite.is_(None), TareaEquipo.fecha_limite,
        TareaEquipo.prioridad != "urgente", TareaEquipo.created_at,
    ).all()

    abiertas = [t for t in todas if t.estado == "pendiente"]
    fin_semana = hoy + timedelta(days=6 - hoy.weekday())

    # El reparto por persona, SIN el filtro puesto: si el contador cambiara al
    # filtrar no serviría para lo que sirve, que es ver de un vistazo quién está
    # enterrado y quién libre antes de repartir nada.
    todas_abiertas = (db.query(TareaEquipo)
                        .filter(TareaEquipo.estado == "pendiente").all())
    cuentas = {n: sum(1 for t in todas_abiertas if t.asignado_a == n) for n in EQUIPO}
    cuentas["todas"] = len(todas_abiertas)

    def bucket(t):
        if not t.fecha_limite:
            return "sin_fecha"
        if t.fecha_limite < hoy:
            return "vencidas"
        if t.fecha_limite == hoy:
            return "de_hoy"
        return "semana" if t.fecha_limite <= fin_semana else "adelante"

    grupos = {k: [] for k in ("vencidas", "de_hoy", "semana", "adelante", "sin_fecha")}
    for t in abiertas:
        grupos[bucket(t)].append(_tarea_json(t))

    # Lo hecho, por semanas y de lo más reciente a lo más antiguo. Mismo criterio
    # que el registro de tareas del CRM para que las dos pantallas hablen de la
    # misma semana.
    hechas = sorted((t for t in todas if t.estado == "hecha" and t.completada_en),
                    key=lambda t: t.completada_en, reverse=True)
    semanas = OrderedDict()
    for t in hechas:
        lunes = _lunes_de(t.completada_en.date())
        if lunes == _lunes_de(hoy):
            etiqueta = "Esta semana"
        elif lunes == _lunes_de(hoy) - timedelta(days=7):
            etiqueta = "La semana pasada"
        else:
            etiqueta = f"Semana del {lunes.strftime('%d/%m')}"
        semanas.setdefault(etiqueta, []).append(_tarea_json(t))

    return templates.TemplateResponse("admin/tareas.html", {
        "request": request, "user": current_user,
        "equipo": EQUIPO, "quien": elegido or "todas", "cuentas": cuentas,
        "grupos": grupos, "semanas": semanas,
        "abiertas": len(abiertas),
        "vencidas": len(grupos["vencidas"]),
        "hechas_semana": sum(1 for t in hechas
                             if _lunes_de(t.completada_en.date()) == _lunes_de(hoy)),
    })


class FraseIn(BaseModel):
    texto: str


@router.post("/tareas")
async def crear_tarea_equipo(
    payload: FraseIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Captura rápida: entra una frase, sale una tarea con dueño y fecha."""
    from app.models import TareaEquipo
    from app.services.tareas_texto import analizar

    frase = (payload.texto or "").strip()
    if not frase:
        raise HTTPException(status_code=422, detail="La tarea está vacía.")

    from app.services.tareas_texto import EQUIPO
    campos = analizar(frase)
    t = TareaEquipo(
        texto=campos["texto"],
        asignado_a=campos["asignado_a"],
        fecha_limite=campos["fecha_limite"],
        prioridad=campos["prioridad"],
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    datos = _tarea_json(t)
    # El HTML de la fila lo monta el servidor con la misma plantilla que usa la
    # página. Si lo montara el JS habría dos versiones del mismo trozo y
    # acabarían separándose sin que nadie se diera cuenta.
    macro = templates.get_template("admin/_eq_fila.html").module
    hoy = datetime.utcnow().date()
    if not t.fecha_limite:
        bloque = "sin_fecha"
    elif t.fecha_limite < hoy:
        bloque = "vencidas"
    elif t.fecha_limite == hoy:
        bloque = "de_hoy"
    elif t.fecha_limite <= hoy + timedelta(days=6 - hoy.weekday()):
        bloque = "semana"
    else:
        bloque = "adelante"
    return JSONResponse({"tarea": datos, "bloque": bloque,
                         "html": str(macro.fila(datos, EQUIPO))})


@router.post("/tareas/{tid}/estado")
async def tarea_equipo_estado(
    tid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Hecha ↔ pendiente. Un solo clic, que es el gesto más frecuente."""
    from app.models import TareaEquipo
    t = db.get(TareaEquipo, tid)
    if t is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    if t.estado == "hecha":
        t.estado, t.completada_en = "pendiente", None
    else:
        t.estado, t.completada_en = "hecha", datetime.utcnow()
    db.commit()
    db.refresh(t)
    return JSONResponse(_tarea_json(t))


@router.post("/tareas/{tid}")
async def tarea_equipo_editar(
    tid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
    campo: str = Form(...),
    valor: str = Form(""),
):
    """Cambia el dueño, la fecha o la prioridad desde la propia fila."""
    from app.models import TareaEquipo
    t = db.get(TareaEquipo, tid)
    if t is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")

    if campo == "asignado_a":
        from app.services.tareas_texto import EQUIPO
        if not valor:
            t.asignado_a = None
        else:
            quien = next((n for n in EQUIPO if n.lower() == valor.lower()), None)
            if quien is None:
                raise HTTPException(status_code=400, detail="Esa persona no es del equipo")
            t.asignado_a = quien
    elif campo == "fecha_limite":
        t.fecha_limite = _fecha_dia(valor)
    elif campo == "prioridad":
        if valor not in TareaEquipo.PRIORIDADES:
            raise HTTPException(status_code=400, detail="Prioridad no válida")
        t.prioridad = valor
    elif campo == "texto":
        nuevo = (valor or "").strip()
        if not nuevo:
            raise HTTPException(status_code=422, detail="La tarea está vacía.")
        t.texto = nuevo[:300]
    elif campo == "notas":
        # Sin tope corto: aquí va lo que haga falta, incluidos enlaces largos
        t.notas = (valor or "").strip()[:5000] or None
    else:
        raise HTTPException(status_code=400, detail="Campo no válido")

    db.commit()
    db.refresh(t)
    return JSONResponse(_tarea_json(t))


@router.delete("/tareas/{tid}")
async def tarea_equipo_borrar(
    tid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.models import TareaEquipo
    t = db.get(TareaEquipo, tid)
    if t is None:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    db.delete(t)
    db.commit()
    return JSONResponse({"borrado": True})


def _fecha_dia(valor: str):
    """"YYYY-MM-DD" a date, o None. Tolerante: lo que no se entiende es None."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
