"""CRM de leads: un tablero de tarjetas que se arrastran entre etapas.

Por qué así y no de otra forma:

Los realtors abandonan los CRMs en semanas. No por desorganizados, sino porque
están hechos para alguien sentado en un escritorio y no para quien va entre
visitas contestando por el móvil. Así que aquí solo el nombre es obligatorio,
apuntar una nota cuesta un campo, y no hay nada más que rellenar.

El campo que hace el trabajo es `ultimo_contacto`. El 74% de los leads que acaban
comprando lo hacen más de seis meses después del primer mensaje, cuando el agente
ya dejó de seguirles; el tablero avisa de a quién llevas días sin tocar, que es
justo lo que se olvida.

Nadie se borra: quien no responde va a "frío" y se revisa de vez en cuando.

De momento solo lo ve el admin.
"""
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Lead, LeadNota, LeadTarea
from app.auth import require_admin

router = APIRouter(prefix="/crm")
templates = Jinja2Templates(directory="app/templates")

# El orden importa: es el que se ve en el tablero, de izquierda a derecha.
ETAPAS = [
    ("nuevo",       "Nuevo",       "Acaba de escribir"),
    ("conversando", "Conversando", "Hablando por DM o WhatsApp"),
    ("cualificado", "Cualificado", "Sabes qué busca y con cuánto"),
    ("propuesta",   "Propuesta",   "Le has enseñado algo concreto"),
    ("cerrado",     "Cerrado",     "Operación hecha"),
    ("frio",        "En frío",     "No responde o no es el momento"),
]
CLAVES = {e[0] for e in ETAPAS}

ORIGENES = ["Instagram", "TikTok", "Facebook", "WhatsApp", "Referido", "Otro"]

# Días sin contacto a partir de los cuales avisamos. En "frío" el ritmo es otro:
# se revisa por trimestres, no por semanas.
AVISO = {"normal": (3, 7), "frio": (60, 120)}


class LeadIn(BaseModel):
    nombre: str
    origen: Optional[str] = None
    contacto: Optional[str] = None
    telefono: Optional[str] = None
    interes: Optional[str] = None
    presupuesto: Optional[str] = None
    etapa: str = "nuevo"


class MoverIn(BaseModel):
    etapa: str
    posicion: int = 0


class NotaIn(BaseModel):
    texto: str


class TareaIn(BaseModel):
    texto: str
    fecha_limite: Optional[str] = None   # "YYYY-MM-DD" o vacío


def _fecha(valor: Optional[str]) -> Optional[datetime]:
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _tarea_json(t: LeadTarea) -> dict:
    hoy = datetime.utcnow().date()
    limite = t.fecha_limite.date() if t.fecha_limite else None
    return {
        "id": t.id,
        "texto": t.texto,
        "fecha_limite": limite.isoformat() if limite else None,
        "hecha": t.hecha,
        # "vencida" solo tiene sentido si está pendiente y tenía fecha
        "vencida": bool(limite and not t.hecha and limite < hoy),
        "hoy": bool(limite and not t.hecha and limite == hoy),
        "completada_en": t.completada_en.strftime("%d/%m/%Y") if t.completada_en else None,
    }


def _mi_lead(lid: int, user: User, db: Session) -> Lead:
    lead = db.query(Lead).filter(Lead.id == lid, Lead.user_id == user.id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    return lead


def _dias(lead: Lead) -> int:
    return (datetime.utcnow() - (lead.ultimo_contacto or lead.created_at)).days


def _json(lead: Lead) -> dict:
    aviso, alerta = AVISO["frio" if lead.etapa == "frio" else "normal"]
    d = _dias(lead)
    return {
        "id": lead.id,
        "nombre": lead.nombre,
        "origen": lead.origen,
        "contacto": lead.contacto,
        "telefono": lead.telefono,
        "interes": lead.interes,
        "presupuesto": lead.presupuesto,
        "etapa": lead.etapa,
        "dias": d,
        # Fecha breve del último contacto: al realtor le dice más "hablamos el
        # 09/09" que "hace 3 días", porque es lo que puede cruzar con su agenda.
        "contacto_fecha": (lead.ultimo_contacto or lead.created_at).strftime("%d/%m"),
        "urgencia": "alta" if d >= alerta else ("media" if d >= aviso else "baja"),
        "notas": len(lead.notas),
        "tareas_pendientes": sum(1 for t in lead.tareas if not t.hecha),
        "tareas_vencidas": sum(
            1 for t in lead.tareas
            if not t.hecha and t.fecha_limite and t.fecha_limite.date() < datetime.utcnow().date()
        ),
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def tablero(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    leads = (
        db.query(Lead)
        .filter(Lead.user_id == current_user.id)
        .order_by(Lead.posicion, Lead.id)
        .all()
    )
    por_etapa = {clave: [] for clave, _, _ in ETAPAS}
    for l in leads:
        por_etapa.setdefault(l.etapa, []).append(_json(l))

    # Los que llevan más tiempo sin tocar, sin contar cerrados
    olvidados = sorted(
        (_json(l) for l in leads if l.etapa != "cerrado"),
        key=lambda x: -x["dias"],
    )
    olvidados = [o for o in olvidados if o["urgencia"] != "baja"][:5]

    return templates.TemplateResponse("crm.html", {
        "request": request,
        "user": current_user,
        "etapas": ETAPAS,
        "origenes": ORIGENES,
        "por_etapa": por_etapa,
        "total": len(leads),
        "olvidados": olvidados,
    })


@router.post("/leads")
async def crear(
    payload: LeadIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    nombre = (payload.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="El lead necesita un nombre.")
    etapa = payload.etapa if payload.etapa in CLAVES else "nuevo"

    lead = Lead(
        user_id=current_user.id,
        nombre=nombre[:150],
        origen=(payload.origen or None),
        contacto=(payload.contacto or "").strip() or None,
        telefono=(payload.telefono or "").strip() or None,
        interes=(payload.interes or "").strip() or None,
        presupuesto=(payload.presupuesto or "").strip() or None,
        etapa=etapa,
        posicion=0,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return JSONResponse({"lead": _json(lead)})


@router.post("/leads/{lid}/mover")
async def mover(
    lid: int,
    payload: MoverIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = _mi_lead(lid, current_user, db)
    if payload.etapa not in CLAVES:
        raise HTTPException(status_code=422, detail="Etapa desconocida")
    lead.etapa = payload.etapa
    lead.posicion = max(0, payload.posicion)
    db.commit()
    return JSONResponse({"lead": _json(lead)})


@router.patch("/leads/{lid}")
async def editar(
    lid: int,
    payload: LeadIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = _mi_lead(lid, current_user, db)
    nombre = (payload.nombre or "").strip()
    if not nombre:
        raise HTTPException(status_code=422, detail="El lead necesita un nombre.")
    lead.nombre = nombre[:150]
    lead.origen = payload.origen or None
    lead.contacto = (payload.contacto or "").strip() or None
    lead.telefono = (payload.telefono or "").strip() or None
    lead.interes = (payload.interes or "").strip() or None
    lead.presupuesto = (payload.presupuesto or "").strip() or None
    db.commit()
    return JSONResponse({"lead": _json(lead)})


@router.get("/leads/{lid}")
async def detalle(
    lid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = _mi_lead(lid, current_user, db)
    return JSONResponse({
        "lead": _json(lead),
        "notas": [
            {"texto": n.texto, "fecha": n.created_at.strftime("%d/%m/%Y · %H:%M")}
            for n in lead.notas
        ],
        "tareas": [_tarea_json(t) for t in
                   sorted(lead.tareas,
                          key=lambda t: (t.hecha, t.fecha_limite or datetime.max))],
    })


@router.post("/leads/{lid}/notas")
async def apuntar(
    lid: int,
    payload: NotaIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = _mi_lead(lid, current_user, db)
    texto = (payload.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=422, detail="La nota está vacía.")
    db.add(LeadNota(lead_id=lead.id, texto=texto))
    # Apuntar una nota ES el contacto: no hay que marcarlo aparte
    lead.ultimo_contacto = datetime.utcnow()
    db.commit()
    db.refresh(lead)
    return JSONResponse({"lead": _json(lead)})


@router.post("/leads/{lid}/contactado")
async def contactado(
    lid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Para cuando hablas con alguien y no hay nada que apuntar."""
    lead = _mi_lead(lid, current_user, db)
    lead.ultimo_contacto = datetime.utcnow()
    db.commit()
    db.refresh(lead)
    return JSONResponse({"lead": _json(lead)})


@router.delete("/leads/{lid}")
async def borrar(
    lid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = _mi_lead(lid, current_user, db)
    db.delete(lead)
    db.commit()
    return JSONResponse({"borrado": True})


# ── Tareas ───────────────────────────────────────────────────────────────────

@router.post("/leads/{lid}/tareas")
async def crear_tarea(
    lid: int,
    payload: TareaIn,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    lead = _mi_lead(lid, current_user, db)
    texto = (payload.texto or "").strip()
    if not texto:
        raise HTTPException(status_code=422, detail="La tarea está vacía.")
    tarea = LeadTarea(lead_id=lead.id, texto=texto[:300],
                      fecha_limite=_fecha(payload.fecha_limite))
    db.add(tarea)
    db.commit()
    db.refresh(tarea)
    db.refresh(lead)
    return JSONResponse({"tarea": _tarea_json(tarea), "lead": _json(lead)})


@router.post("/tareas/{tid}/toggle")
async def marcar_tarea(
    tid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tarea = (
        db.query(LeadTarea).join(Lead)
        .filter(LeadTarea.id == tid, Lead.user_id == current_user.id)
        .first()
    )
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    tarea.hecha = not tarea.hecha
    # La fecha de cierre es lo que alimenta el registro de "lo que llevo hecho"
    tarea.completada_en = datetime.utcnow() if tarea.hecha else None
    db.commit()
    db.refresh(tarea)
    lead = db.query(Lead).filter(Lead.id == tarea.lead_id).first()
    return JSONResponse({"tarea": _tarea_json(tarea), "lead": _json(lead)})


@router.delete("/tareas/{tid}")
async def borrar_tarea(
    tid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tarea = (
        db.query(LeadTarea).join(Lead)
        .filter(LeadTarea.id == tid, Lead.user_id == current_user.id)
        .first()
    )
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    db.delete(tarea)
    db.commit()
    return JSONResponse({"borrado": True})


@router.get("/tareas", response_class=HTMLResponse)
async def registro(
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lo que queda por hacer y, sobre todo, lo que ya se ha hecho.

    Ver el trabajo acumulado es lo que sostiene el hábito: en este negocio los
    resultados tardan meses en llegar, y sin un registro de lo hecho solo queda
    la sensación de que no avanzas."""
    tareas = (
        db.query(LeadTarea).join(Lead)
        .filter(Lead.user_id == current_user.id)
        .order_by(LeadTarea.fecha_limite.is_(None), LeadTarea.fecha_limite)
        .all()
    )
    nombres = {l.id: l.nombre for l in db.query(Lead).filter(Lead.user_id == current_user.id).all()}
    hoy = datetime.utcnow().date()

    def fila(t):
        return {**_tarea_json(t), "lead": nombres.get(t.lead_id, "—"), "lead_id": t.lead_id}

    pendientes = [fila(t) for t in tareas if not t.hecha]
    vencidas = [p for p in pendientes if p["vencida"]]
    de_hoy   = [p for p in pendientes if p["hoy"]]
    proximas = [p for p in pendientes if not p["vencida"] and not p["hoy"]]

    # Hechas, agrupadas por semana, de más reciente a más antigua
    hechas = sorted((t for t in tareas if t.hecha and t.completada_en),
                    key=lambda t: t.completada_en, reverse=True)
    semanas = OrderedDict()
    for t in hechas:
        d = t.completada_en.date()
        lunes = d - timedelta(days=d.weekday())
        if lunes == hoy - timedelta(days=hoy.weekday()):
            etiqueta = "Esta semana"
        elif lunes == hoy - timedelta(days=hoy.weekday() + 7):
            etiqueta = "La semana pasada"
        else:
            etiqueta = f"Semana del {lunes.strftime('%d/%m')}"
        semanas.setdefault(etiqueta, []).append(fila(t))

    inicio_mes = hoy.replace(day=1)
    return templates.TemplateResponse("crm_tareas.html", {
        "request": request,
        "user": current_user,
        "vencidas": vencidas,
        "de_hoy": de_hoy,
        "proximas": proximas,
        "semanas": semanas,
        "hechas_semana": sum(1 for t in hechas
                             if t.completada_en.date() >= hoy - timedelta(days=hoy.weekday())),
        "hechas_mes": sum(1 for t in hechas if t.completada_en.date() >= inicio_mes),
        "total_hechas": len(hechas),
    })
