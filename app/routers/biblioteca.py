"""Biblioteca de Respuestas.

De las llamadas 1-a-1 con los alumnos salen explicaciones que valen para todos.
En vez de quedarse enterradas en una grabación de 40 minutos, aquí está cada una
recortada, con título y agrupada por alumno.

Solo la ve el admin: las grabaciones llevan la cara del alumno, su nombre y sus
cifras de negocio.
"""
from collections import OrderedDict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, ClipReunion
from app.auth import require_admin

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Orden fijo: los alumnos activos primero y siempre igual, para que el admin
# sepa dónde mirar sin leer.
ORDEN_ALUMNOS = ["Ada", "Rackson", "Luis"]


@router.get("/biblioteca", response_class=HTMLResponse)
async def biblioteca(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    clips = (
        db.query(ClipReunion)
        .order_by(ClipReunion.alumno, ClipReunion.fecha_reunion, ClipReunion.inicio_seg)
        .all()
    )

    por_alumno = OrderedDict((a, []) for a in ORDEN_ALUMNOS)
    for c in clips:
        por_alumno.setdefault(c.alumno, []).append(c)
    por_alumno = OrderedDict((a, cs) for a, cs in por_alumno.items() if cs)

    # Un tema que sale con varios alumnos es señal de que conviene llevarlo a la
    # formación, en vez de repetirlo llamada tras llamada.
    temas = {}
    for c in clips:
        if c.tema:
            temas.setdefault(c.tema, set()).add(c.alumno)
    repetidos = sorted(
        ((t, sorted(a)) for t, a in temas.items() if len(a) > 1),
        key=lambda x: -len(x[1]),
    )

    # Enlace a la carpeta de cada alumno en Drive, sacado de sus propios clips
    carpetas = {a: next((c.carpeta_url for c in cs if c.carpeta_url), None)
                for a, cs in por_alumno.items()}

    return templates.TemplateResponse("biblioteca.html", {
        "request": request,
        "user": current_user,
        "por_alumno": por_alumno,
        "carpetas": carpetas,
        "total": len(clips),
        "minutos": round(sum(c.duracion_seg for c in clips) / 60),
        "repetidos": repetidos,
    })
