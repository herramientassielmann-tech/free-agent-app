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
