"""Las tareas que se repiten cada semana, y cómo se convierten en tareas reales.

Una tarea fija (`TareaFija`) es una plantilla: «subir los reels del lunes». No
se marca ni se anota. Lo que se marca es la **copia** de esta semana, que vive
en `tareas_equipo` como cualquier otra tarea.

Por qué una copia por semana y no reutilizar la misma fila:

  · Lo hecho la semana pasada sigue estando hecho. Si se reutilizara la fila
    habría que desmarcarla cada lunes, y entonces el registro —que es justo lo
    que se quiere conservar— se borraría solo cada siete días.
  · Cambiar la lista de fijas no reescribe el pasado. Quitar una fija hoy no
    hace desaparecer las semanas en que sí se hizo.

Las copias se crean **al abrir la página**, no con un temporizador. Es una
pieza menos en el servidor y el efecto es idéntico: si nadie abre la página,
nadie estaba esperando las tareas.
"""
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import TareaEquipo, TareaFija

log = logging.getLogger(__name__)


# El icono se deduce de la dirección en vez de elegirse a mano: una cosa menos
# que rellenar, y una cosa menos que se puede rellenar mal.
ICONOS = (
    ("docs.google.com",   "gdoc"),
    ("drive.google.com",  "gdoc"),
    ("metricool.com",     "metricool"),
    ("wa.me",             "whatsapp"),
    ("whatsapp.com",      "whatsapp"),
)


def icono_de(url: Optional[str]) -> Optional[str]:
    """Qué dibujo le toca a esa dirección. `enlace` genérico si no es ninguna."""
    if not url:
        return None
    bajo = url.lower()
    for trozo, nombre in ICONOS:
        if trozo in bajo:
            return nombre
    return "enlace"


def lunes_de(d: date) -> date:
    """El lunes de la semana de esa fecha. Mismo criterio que el resto de la app."""
    return d - timedelta(days=d.weekday())


def asegurar_semana(db: Session, persona: Optional[str] = None,
                    hoy: Optional[date] = None) -> int:
    """Deja creada la copia de esta semana de cada fija activa. Devuelve cuántas creó.

    Es idempotente: llamarla cien veces el mismo lunes crea las tareas una vez.
    Lo garantiza un índice único sobre (fija_id, semana), no una comprobación
    previa: dos pestañas abiertas a la vez llegan a la vez, y la comprobación
    previa las dejaría pasar a las dos. Se intenta insertar y se deja que la
    base de datos diga que ya estaba.
    """
    hoy = hoy or date.today()
    lunes = lunes_de(hoy)

    consulta = db.query(TareaFija).filter(TareaFija.activa.is_(True))
    if persona:
        consulta = consulta.filter(TareaFija.asignado_a == persona)
    fijas = consulta.order_by(TareaFija.orden, TareaFija.id).all()
    if not fijas:
        return 0

    # Las que ya existen, de una sola consulta: lo normal es que estén todas y
    # no haya que insertar nada, y ese camino tiene que ser barato.
    ya = {(fid, per) for fid, per in
          db.query(TareaEquipo.fija_id, TareaEquipo.periodo)
            .filter(TareaEquipo.semana == lunes,
                    TareaEquipo.fija_id.isnot(None)).all()}

    creadas = 0
    nacimiento = {f.id: (f.created_at.date() if f.created_at else None) for f in fijas}

    for f in fijas:
        for periodo, fecha in _repeticiones(f, lunes, hoy):
            if (f.id, periodo) in ya:
                continue
            # Una fija de los lunes creada un viernes NO se crea para esta
            # semana: saldría ya vencida el día de estrenarla, por un lunes en
            # el que aún no existía. Empieza en la siguiente repetición.
            #
            # Mira la FECHA de entrega, no el periodo. Una fija sin día concreto
            # tiene el lunes por periodo pero no tiene fecha: vale para toda la
            # semana y todavía se puede hacer, así que esa sí se crea hoy.
            nace = nacimiento.get(f.id)
            if fecha is not None and nace and fecha < nace:
                continue

            try:
                db.add(TareaEquipo(
                    texto=f.texto,
                    asignado_a=f.asignado_a,
                    # Sin día concreto la copia sale sin fecha y vale para toda
                    # la semana. Una fecha inventada sólo haría que venciera.
                    fecha_limite=fecha,
                    prioridad=f.prioridad,
                    fija_id=f.id,
                    semana=lunes,
                    periodo=periodo,
                    enlace=f.enlace,
                    enlace_icono=f.enlace_icono,
                ))
                db.commit()
                creadas += 1
            except IntegrityError:
                # Otra pestaña se adelantó. Es el caso normal, no un fallo.
                db.rollback()
            except Exception:                                # noqa: BLE001
                # Que una fija rara no deje sin el resto de su semana.
                db.rollback()
                log.exception("No se pudo crear la copia de la tarea fija %s", f.id)

    return creadas


def _repeticiones(f: TareaFija, lunes: date, hoy: date):
    """Qué copias le tocan a esta fija en la semana en curso: (periodo, fecha).

    Una semanal tiene una. Una diaria tiene una por día **ya empezado**: del
    lunes a hoy, no la semana entera. Se rellenan los días pasados a propósito,
    aunque nadie abriera la página: si el martes no se publicó, el martes tiene
    que verse sin marcar. Un hueco no cuenta nada; una tarea vencida sí.
    """
    if not f.cada_dia:
        fecha = (lunes + timedelta(days=f.dia_semana)
                 if f.dia_semana is not None else None)
        return [(lunes, fecha)]
    # En una diaria el periodo y la fecha límite son el mismo día.
    dias = [lunes + timedelta(days=i) for i in range((hoy - lunes).days + 1)]
    return [(d, d) for d in dias]
