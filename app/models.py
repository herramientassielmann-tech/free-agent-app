from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import (
    Integer, String, Boolean, Text, DateTime, ForeignKey, Enum as SAEnum
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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    profile: Mapped[Optional["RealtorProfile"]] = relationship("RealtorProfile", back_populates="user", uselist=False)
    scripts: Mapped[List["Script"]] = relationship("Script", back_populates="user")


class RealtorProfile(Base):
    __tablename__ = "realtor_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
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

    user: Mapped["User"] = relationship("User", back_populates="profile")


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    original_transcript: Mapped[Optional[str]] = mapped_column(Text)
    hook: Mapped[Optional[str]] = mapped_column(Text)
    development: Mapped[Optional[str]] = mapped_column(Text)
    conclusion: Mapped[Optional[str]] = mapped_column(Text)
    caption: Mapped[Optional[str]] = mapped_column(Text)
    custom_instructions: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="scripts")
