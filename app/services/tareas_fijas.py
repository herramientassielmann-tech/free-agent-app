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
    ya = {f for (f,) in db.query(TareaEquipo.fija_id)
                          .filter(TareaEquipo.semana == lunes,
                                  TareaEquipo.fija_id.isnot(None)).all()}

    creadas = 0
    for f in fijas:
        if f.id in ya:
            continue

        fecha = (lunes + timedelta(days=f.dia_semana)
                 if f.dia_semana is not None else None)
        # Una fija de los lunes creada un viernes NO se crea para esta semana:
        # saldría ya vencida el día de estrenarla, por un lunes en el que aún
        # no existía. Empieza el lunes que viene. Sólo afecta a la semana en
        # que se crea: a partir de ahí la fecha siempre es posterior.
        if fecha is not None and f.created_at and fecha < f.created_at.date():
            continue

        try:
            db.add(TareaEquipo(
                texto=f.texto,
                asignado_a=f.asignado_a,
                # Sin día concreto la copia sale sin fecha y vale para toda la
                # semana. Ponerle una fecha inventada sólo haría que venciera.
                fecha_limite=fecha,
                prioridad=f.prioridad,
                fija_id=f.id,
                semana=lunes,
            ))
            db.commit()
            creadas += 1
        except IntegrityError:
            # Otra pestaña se adelantó. Es el caso normal, no un fallo.
            db.rollback()
        except Exception:                                    # noqa: BLE001
            # Que una fija rara no deje a la persona sin el resto de su semana.
            db.rollback()
            log.exception("No se pudo crear la copia de la tarea fija %s", f.id)

    return creadas
