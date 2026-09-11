from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Integer, String, Boolean, Text, DateTime, ForeignKey, Enum as SAEnum,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
from app.database import Base


class ToneEnum(str, enum.Enum):
    formal = "formal"
    cercano = "cercano"
    energetico = "energetico"
    inspiracional = "inspiracional"


class SpecializationEnum(str, enum.Enum):
    primera_vivienda = "primera_vivienda"
    lujo = "lujo"
    inversion = "inversion"
    comercial = "comercial"
    todo_tipo = "todo_tipo"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    temp_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    profiles: Mapped[List["RealtorProfile"]] = relationship(
        "RealtorProfile", back_populates="user", order_by="RealtorProfile.id"
    )
    scripts: Mapped[List["Script"]] = relationship("Script", back_populates="user")
    lead_conversations: Mapped[List["LeadConversation"]] = relationship(
        "LeadConversation", back_populates="user"
    )

    @property
    def profile(self) -> Optional["RealtorProfile"]:
        """Devuelve el perfil activo (compatibilidad con el resto del código)."""
        for p in self.profiles:
            if p.is_active:
                return p
        return self.profiles[0] if self.profiles else None


class RealtorProfile(Base):
    __tablename__ = "realtor_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(100), default="Mi Perfil", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    market: Mapped[Optional[str]] = mapped_column(String(100))
    tone: Mapped[str] = mapped_column(
        SAEnum(ToneEnum), default=ToneEnum.cercano, nullable=False
    )
    speaking_notes: Mapped[Optional[str]] = mapped_column(Text)
    specialization: Mapped[str] = mapped_column(
        SAEnum(SpecializationEnum), default=SpecializationEnum.todo_tipo, nullable=False
    )
    about_me: Mapped[Optional[str]] = mapped_column(Text)
    # Campos ampliados (se rellenan desde la transcripción de la llamada de onboarding)
    cliente_ideal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objeciones: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    casos_exito: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    objetivo_cta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    temas_evitar: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="profiles")


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    original_transcript: Mapped[Optional[str]] = mapped_column(Text)
    hook: Mapped[Optional[str]] = mapped_column(Text)
    promesa: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    development: Mapped[Optional[str]] = mapped_column(Text)
    conclusion: Mapped[Optional[str]] = mapped_column(Text)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    estructura_detectada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Versión editada por el realtor en el editor de guiones. JSON con las
    # secciones {hook, development, conclusion, caption}. El guión original
    # generado por la IA nunca se toca, para poder restaurarlo.
    edicion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="scripts")


class StarterScript(Base):
    """Guión de las "ideas iniciales": contenido común de la academia, igual
    para todos los realtors. Se genera una sola vez a partir de un vídeo de
    referencia y queda fijo; los realtors solo lo consultan y lo marcan."""
    __tablename__ = "starter_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # orden 1..N
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    titulo: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    hook: Mapped[Optional[str]] = mapped_column(Text)
    development: Mapped[Optional[str]] = mapped_column(Text)
    conclusion: Mapped[Optional[str]] = mapped_column(Text)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    estructura_detectada: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    checks: Mapped[List["StarterScriptCheck"]] = relationship(
        "StarterScriptCheck", back_populates="script", cascade="all, delete-orphan"
    )


class StarterScriptCheck(Base):
    """Marca de "ya lo he hecho" de UN realtor sobre UN guión inicial.
    Cada realtor lleva su propio progreso sobre los mismos guiones."""
    __tablename__ = "starter_script_checks"
    __table_args__ = (
        UniqueConstraint("user_id", "starter_script_id", name="uq_starter_check_user_script"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    starter_script_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("starter_scripts.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    script: Mapped["StarterScript"] = relationship("StarterScript", back_populates="checks")


class StarterScriptEdit(Base):
    """Copia personal de UN realtor sobre UN guión inicial.

    Los guiones de "Ideas Iniciales" son comunes a todos, así que la edición no
    puede tocar el original: cada realtor guarda aquí su propia versión y solo
    él la ve. Si no hay fila, ese realtor todavía ve el guión tal cual."""
    __tablename__ = "starter_script_edits"
    __table_args__ = (
        UniqueConstraint("user_id", "starter_script_id", name="uq_starter_edit_user_script"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    starter_script_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("starter_scripts.id"), nullable=False, index=True
    )
    # JSON con las secciones {hook, development, conclusion, caption}
    edicion: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class Lead(Base):
    """Una persona que ha contactado al realtor. El CRM más simple posible.

    Decisiones de diseño, sacadas de por qué los realtors abandonan los CRMs:
      - Pocos campos. Solo el nombre es obligatorio; todo lo demás se rellena
        cuando se sabe. Un formulario de doce campos no se rellena nunca.
      - `ultimo_contacto` es el campo que de verdad importa: el 74% de los leads
        que acaban comprando lo hacen más de seis meses después, cuando el agente
        ya dejó de seguirles. El tablero avisa de a quién llevas días sin tocar.
      - Nadie se borra. Los que no responden van a "frío", no a la papelera.
    """
    __tablename__ = "leads"

    ETAPAS = ("nuevo", "conversando", "cualificado", "propuesta", "cerrado", "frio")

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"),
                                         nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    origen: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    contacto: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    interes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    presupuesto: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    etapa: Mapped[str] = mapped_column(String(20), nullable=False, default="nuevo", index=True)
    posicion: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Se actualiza al crear el lead y cada vez que se apunta una nota
    ultimo_contacto: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    notas: Mapped[List["LeadNota"]] = relationship(
        "LeadNota", back_populates="lead",
        order_by="LeadNota.created_at.desc()", cascade="all, delete-orphan",
    )
    tareas: Mapped[List["LeadTarea"]] = relationship(
        "LeadTarea", back_populates="lead",
        order_by="LeadTarea.hecha, LeadTarea.fecha_limite", cascade="all, delete-orphan",
    )
    contactos: Mapped[List["LeadContacto"]] = relationship(
        "LeadContacto", back_populates="lead",
        order_by="LeadContacto.fecha.desc()", cascade="all, delete-orphan",
    )


class LeadTarea(Base):
    """Algo pendiente con un lead: llamar el martes, mandar el brochure, etc.

    Se guarda `completada_en` además del booleano porque el valor no está solo
    en saber qué queda por hacer, sino en poder mirar atrás y ver lo que has
    hecho esta semana y este mes. Sin la fecha de cierre ese registro no existe.
    """
    __tablename__ = "lead_tareas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"),
                                         nullable=False, index=True)
    texto: Mapped[str] = mapped_column(String(300), nullable=False)
    # Sin fecha es una tarea suelta; con fecha entra en los avisos de vencidas
    fecha_limite: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    hecha: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    completada_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Se marca cuando se avisa por email, para no avisar dos veces de lo mismo
    avisada_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="tareas")


class LeadContacto(Base):
    """Un tick de seguimiento: una vez que el realtor habló con este lead.

    `Lead.ultimo_contacto` guarda solo la última fecha y la sobrescribe, así que
    sirve para avisar de a quién llevas días sin tocar pero no puede enseñar la
    cadena. Y la cadena es justo lo que sostiene el hábito: ver siete ticks
    seguidos convence de que estás haciendo el seguimiento mucho más que un
    "hace 3 días" que mañana dirá otra cosa.

    Se crea tanto al pulsar "he hablado" como al apuntar una nota, porque
    apuntar algo ES haber hablado. Así el tick de arriba y `ultimo_contacto`
    nunca se contradicen.
    """
    __tablename__ = "lead_contactos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"),
                                         nullable=False, index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow,
                                            nullable=False, index=True)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="contactos")


class LeadNota(Base):
    """Lo que pasó en un contacto. Escribir una nota tiene que costar segundos."""
    __tablename__ = "lead_notas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    lead_id: Mapped[int] = mapped_column(Integer, ForeignKey("leads.id"),
                                         nullable=False, index=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    lead: Mapped["Lead"] = relationship("Lead", back_populates="notas")


class ClipReunion(Base):
    """Un trozo de una llamada 1-a-1 donde se resuelve una duda concreta.

    De las llamadas con los alumnos salen explicaciones que sirven para todos:
    cómo perder el miedo a la cámara, por qué no aprender a editar, qué CTA usar.
    Aquí queda cada una recortada y con título, agrupada por alumno.

    El fichero vive en Drive, no en el servidor: son grabaciones con la cara y
    los datos del alumno, y ocupan. Aquí solo se guarda el enlace."""
    __tablename__ = "clips_reunion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alumno: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(300), nullable=False)
    resumen: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tema: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    # De qué reunión sale y en qué momento
    fecha_reunion: Mapped[str] = mapped_column(String(20), nullable=False)
    inicio_seg: Mapped[int] = mapped_column(Integer, nullable=False)
    duracion_seg: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # 'video' | 'audio'
    drive_id: Mapped[str] = mapped_column(String(120), nullable=False)
    drive_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # Carpeta del alumno en Drive. Se repite en cada clip suyo a propósito: así
    # el enlace a la carpeta sale de los propios datos y no hay que mantener
    # una tabla aparte que se desincronice.
    carpeta_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LeadConversation(Base):
    """Un hilo de chat con un lead concreto: el realtor pega lo que dice el
    cliente y recibe una sugerencia de respuesta. Nunca se envía nada solo."""
    __tablename__ = "lead_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    lead_name: Mapped[str] = mapped_column(String(150), nullable=False)
    lead_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    user: Mapped["User"] = relationship("User", back_populates="lead_conversations")
    messages: Mapped[List["LeadMessage"]] = relationship(
        "LeadMessage", back_populates="conversation",
        order_by="LeadMessage.id", cascade="all, delete-orphan",
    )


class LeadMessage(Base):
    __tablename__ = "lead_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("lead_conversations.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'cliente' | 'sugerencia'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Solo en 'sugerencia': aviso para el realtor cuando falta contexto para
    # responder mejor. Nunca se manda al cliente, no forma parte del mensaje.
    nota: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["LeadConversation"] = relationship(
        "LeadConversation", back_populates="messages"
    )


# ── Alta de alumnos (onboarding) ─────────────────────────────────────────────

class Alta(Base):
    """El expediente de entrada de un alumno: de agendar la llamada a estar dentro.

    Antes esto no existía en ningún sitio. Se daba de alta a mano, la contraseña
    se mandaba por WhatsApp y no quedaba constancia de que nadie hubiera firmado
    ni pagado. Con seis alumnos eso se lleva en la cabeza; con quince, no.

    Cada paso guarda su FECHA, no un booleano. Un "sí" no dice cuándo pasó, y sin
    el cuándo no se puede ver quién lleva tres días atascado, que es justo lo que
    hay que mirar.
    """
    __tablename__ = "altas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # La hora exacta de la llamada de venta: el correo de bienvenida sale
    # justo entonces, para que el cierre se haga en vivo durante la llamada.
    programada_para: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    # Identificador de Calendly. Si reagenda llega el mismo y se actualiza la
    # fila en vez de crear un alta duplicada.
    calendly_uri: Mapped[Optional[str]] = mapped_column(String(300), nullable=True, unique=True)

    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_expira: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    email_enviado_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pagado_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    contrato_firmado_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cuenta_creada_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    skool_abierto_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    onboarding_agendado_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Para abrirle los accesos a mano cuando estás con él en la llamada y el
    # cobro va por transferencia o por el 50/50.
    desbloqueado_a_mano: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metodo_pago: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # tarjeta|ach|manual
    stripe_session: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    recordatorios_enviados: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    firma: Mapped[Optional["FirmaContrato"]] = relationship(
        "FirmaContrato", back_populates="alta", uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def accesos_abiertos(self) -> bool:
        """Si puede crear cuenta, entrar a Skool y agendar el onboarding.

        No se entrega el producto antes de cobrar. El desbloqueo a mano existe
        porque a veces el cobro va por fuera y el alumno está delante.
        """
        return bool(self.pagado_en or self.desbloqueado_a_mano)

    @property
    def completada(self) -> bool:
        return bool(self.pagado_en and self.contrato_firmado_en and self.cuenta_creada_en)


class FirmaContrato(Base):
    """La firma del contrato y su rastro de auditoría.

    Va en su propia tabla y no como campos del Alta a propósito: esto es un
    registro legal y no debe mezclarse con el estado operativo, que cambia.

    La E-SIGN Act pide cinco cosas para que una firma electrónica se sostenga:
    consentimiento, intención, atribución, conservación y exactitud. Por eso se
    guarda el consentimiento aparte y con su fecha (tiene que ser ANTERIOR a la
    firma), y por eso se congela el HTML exacto que la persona vio junto con su
    huella: sin eso no se puede demostrar QUÉ firmó, sólo que firmó algo.
    """
    __tablename__ = "firmas_contrato"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    alta_id: Mapped[int] = mapped_column(Integer, ForeignKey("altas.id"),
                                         nullable=False, unique=True, index=True)

    nombre_firmante: Mapped[str] = mapped_column(String(150), nullable=False)
    documento_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    domicilio: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    # E-SIGN: aceptó expresamente firmar en electrónico, tras leer que tiene
    # derecho a una copia en papel y a retirar el consentimiento.
    consentimiento_electronico: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consentimiento_en: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    reconocimientos: Mapped[str] = mapped_column(Text, nullable=False)  # JSON de las 4 casillas
    ip: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)

    huella_documento: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256
    version_contrato: Mapped[str] = mapped_column(String(20), nullable=False, default="v1.0")
    html_firmado: Mapped[str] = mapped_column(Text, nullable=False)

    firmado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    alta: Mapped["Alta"] = relationship("Alta", back_populates="firma")


class AccesoRegistrado(Base):
    """Cada entrada de un alumno a la herramienta.

    No se enseña en ninguna pantalla y no sirve para vigilar a nadie: para ganar
    una reclamación de cargo hacen falta tres cosas —contrato firmado, registro
    de IP y prueba de que la persona accedió al producto—, y esta tabla es la
    tercera. Con pagos de 3.000 dólares y sin devoluciones, no es un extra.
    """
    __tablename__ = "accesos_registrados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"),
                                         nullable=False, index=True)
    ip: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    entrado_en: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
