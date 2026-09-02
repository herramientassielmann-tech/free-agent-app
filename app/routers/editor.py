"""Editor de guiones.

Un guión generado es un punto de partida, no un texto definitivo: el realtor
tiene que adaptarlo a su forma de hablar. Aquí puede editarlo por secciones,
manteniendo la estructura de la metodología (hook / desarrollo / CTA / caption),
y sacarlo en PDF con el branding de la academia.

El original generado NUNCA se sobrescribe. La edición se guarda aparte, así que
siempre se puede volver atrás.

De momento solo lo ve el admin (require_admin). Cuando se valide, basta con
cambiar la dependencia a get_current_user.
"""
import json
from datetime import datetime
from html.parser import HTMLParser
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Script, StarterScript, StarterScriptEdit
from app.auth import require_admin

router = APIRouter(prefix="/editor")
templates = Jinja2Templates(directory="app/templates")

SECCIONES = ("hook", "development", "conclusion", "caption")

# El editor guarda HTML (negrita, cursiva, listas). Se limpia SIEMPRE en el
# servidor: sin esto, un guión guardado podría ejecutar código en el navegador
# de quien lo abra después — incluido el admin al revisar el guión de un realtor.
ETIQUETAS_OK = {"b", "strong", "i", "em", "u", "br", "p", "div", "ul", "ol", "li"}
ETIQUETAS_VACIAS = {"br"}


class _Limpiador(HTMLParser):
    """Deja pasar solo etiquetas de formato, sin ningún atributo."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self.abiertas: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ETIQUETAS_OK:
            if tag in ETIQUETAS_VACIAS:
                self.partes.append(f"<{tag}>")
            else:
                self.partes.append(f"<{tag}>")
                self.abiertas.append(tag)

    def handle_endtag(self, tag):
        if tag in ETIQUETAS_OK and tag not in ETIQUETAS_VACIAS and tag in self.abiertas:
            # cerramos hasta la etiqueta correspondiente para no dejar HTML roto
            while self.abiertas:
                abierta = self.abiertas.pop()
                self.partes.append(f"</{abierta}>")
                if abierta == tag:
                    break

    def handle_data(self, data):
        self.partes.append(
            data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )

    def resultado(self) -> str:
        cierres = "".join(f"</{t}>" for t in reversed(self.abiertas))
        return "".join(self.partes) + cierres


def limpiar_html(bruto: str) -> str:
    limpiador = _Limpiador()
    limpiador.feed(bruto or "")
    limpiador.close()
    return limpiador.resultado().strip()


class GuardarRequest(BaseModel):
    hook: str = ""
    development: str = ""
    conclusion: str = ""
    caption: str = ""

    def as_dict(self) -> dict:
        return {s: limpiar_html(getattr(self, s) or "") for s in SECCIONES}


def _leer_edicion(raw: Optional[str]) -> Optional[dict]:
    """La edición guardada, o None si no hay o está corrupta."""
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return d if isinstance(d, dict) else None


def _secciones(original: dict, edicion: Optional[dict]) -> dict:
    """Lo que se muestra en el editor: la edición si existe, si no el original."""
    if not edicion:
        return dict(original)
    return {s: edicion.get(s, original.get(s, "")) or "" for s in SECCIONES}


def _mi_script(sid: int, user: User, db: Session) -> Script:
    script = (
        db.query(Script)
        .filter(Script.id == sid, Script.user_id == user.id)
        .first()
    )
    if not script:
        raise HTTPException(status_code=404, detail="Guión no encontrado")
    return script


# ─────────────────────────── Guiones generados ───────────────────────────

@router.get("/guion/{sid}", response_class=HTMLResponse)
async def editar_guion(
    sid: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    script = _mi_script(sid, current_user, db)
    original = {
        "hook": script.hook or "",
        "development": script.development or "",
        "conclusion": script.conclusion or "",
        "caption": script.caption or "",
    }
    edicion = _leer_edicion(script.edicion)

    return templates.TemplateResponse("editor.html", {
        "request": request,
        "user": current_user,
        "titulo": "Guión",
        "subtitulo": script.source_url,
        "source_url": script.source_url,
        "thumbnail_path": script.thumbnail_path,
        "estructura_detectada": script.estructura_detectada,
        "secciones": _secciones(original, edicion),
        "original": original,
        "editado": bool(edicion),
        "url_guardar": f"/editor/guion/{script.id}/guardar",
        "url_restaurar": f"/editor/guion/{script.id}/restaurar",
        "url_volver": "/history",
    })


@router.post("/guion/{sid}/guardar")
async def guardar_guion(
    sid: int,
    payload: GuardarRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    script = _mi_script(sid, current_user, db)
    script.edicion = json.dumps(payload.as_dict(), ensure_ascii=False)
    script.edited_at = datetime.utcnow()
    db.commit()
    return JSONResponse({"guardado": True, "editado": True})


@router.post("/guion/{sid}/restaurar")
async def restaurar_guion(
    sid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    script = _mi_script(sid, current_user, db)
    script.edicion = None
    script.edited_at = None
    db.commit()
    return JSONResponse({
        "restaurado": True,
        "secciones": {
            "hook": script.hook or "",
            "development": script.development or "",
            "conclusion": script.conclusion or "",
            "caption": script.caption or "",
        },
    })


# ────────────────── Ideas iniciales (copia personal) ──────────────────

@router.get("/idea/{sid}", response_class=HTMLResponse)
async def editar_idea(
    sid: int,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    idea = db.query(StarterScript).filter(StarterScript.id == sid).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea no encontrada")

    original = {
        "hook": idea.hook or "",
        "development": idea.development or "",
        "conclusion": idea.conclusion or "",
        "caption": idea.caption or "",
    }
    fila = (
        db.query(StarterScriptEdit)
        .filter(
            StarterScriptEdit.user_id == current_user.id,
            StarterScriptEdit.starter_script_id == idea.id,
        )
        .first()
    )
    edicion = _leer_edicion(fila.edicion) if fila else None

    return templates.TemplateResponse("editor.html", {
        "request": request,
        "user": current_user,
        "titulo": idea.titulo or "Idea inicial",
        "subtitulo": idea.source_url,
        "source_url": idea.source_url,
        "thumbnail_path": idea.thumbnail_path,
        "estructura_detectada": idea.estructura_detectada,
        "secciones": _secciones(original, edicion),
        "original": original,
        "editado": bool(edicion),
        "url_guardar": f"/editor/idea/{idea.id}/guardar",
        "url_restaurar": f"/editor/idea/{idea.id}/restaurar",
        "url_volver": f"/ideas-iniciales/{idea.id}",
    })


@router.post("/idea/{sid}/guardar")
async def guardar_idea(
    sid: int,
    payload: GuardarRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    idea = db.query(StarterScript).filter(StarterScript.id == sid).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea no encontrada")

    fila = (
        db.query(StarterScriptEdit)
        .filter(
            StarterScriptEdit.user_id == current_user.id,
            StarterScriptEdit.starter_script_id == idea.id,
        )
        .first()
    )
    contenido = json.dumps(payload.as_dict(), ensure_ascii=False)
    if fila:
        fila.edicion = contenido
    else:
        db.add(StarterScriptEdit(
            user_id=current_user.id,
            starter_script_id=idea.id,
            edicion=contenido,
        ))
    db.commit()
    return JSONResponse({"guardado": True, "editado": True})


@router.post("/idea/{sid}/restaurar")
async def restaurar_idea(
    sid: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    idea = db.query(StarterScript).filter(StarterScript.id == sid).first()
    if not idea:
        raise HTTPException(status_code=404, detail="Idea no encontrada")

    fila = (
        db.query(StarterScriptEdit)
        .filter(
            StarterScriptEdit.user_id == current_user.id,
            StarterScriptEdit.starter_script_id == idea.id,
        )
        .first()
    )
    if fila:
        db.delete(fila)
        db.commit()

    return JSONResponse({
        "restaurado": True,
        "secciones": {
            "hook": idea.hook or "",
            "development": idea.development or "",
            "conclusion": idea.conclusion or "",
            "caption": idea.caption or "",
        },
    })
