"""Modelos SQLAlchemy de Blas — conversaciones y mensajes del asistente
comercial por WhatsApp. Usan el mismo `Base` (y por tanto la misma base de
datos Postgres) que el resto de EPi — `app.db.database.Base.metadata.
create_all()` en app/main.py crea tambien estas tablas automaticamente. Los
nombres de tabla (`conversations`, `messages`) no chocan con las de EPi
(`pumps_catalog`, `spare_parts_catalog`, `users`, `leads`)."""
from __future__ import annotations

import enum
import uuid

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum, Boolean, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, CHAR

from app.db.database import Base


class GUID(TypeDecorator):
    """UUID que funciona tanto en Postgres (produccion) como en SQLite
    (desarrollo local sin Docker)."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(str(value))


class ConversationState(str, enum.Enum):
    AWAITING_PHONE = "awaiting_phone"                # solo en el widget web, antes de tener telefono
    AWAITING_NEED = "awaiting_need"                   # ya se mando el whatsapp de apertura, esperando que cuente que necesita
    AWAITING_NAME = "awaiting_name"
    AWAITING_APPLICATION = "awaiting_application"      # aplicacion de la bomba / fluido a controlar
    AWAITING_DELIVERY_CHOICE = "awaiting_delivery_choice"  # email para la oferta, o por whatsapp
    AWAITING_PURCHASING_EMAIL = "awaiting_purchasing_email"
    QUALIFIED = "qualified"                            # lead completo, notificado al equipo


class Channel(str, enum.Enum):
    WEB = "web"
    WHATSAPP = "whatsapp"


class DeliveryChannel(str, enum.Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    # Identificador estable de la sesion del widget (localStorage en el
    # navegador) — permite recuperar la conversacion en el widget mientras
    # todavia no se conoce el telefono (estado AWAITING_PHONE).
    web_session_id = Column(String, unique=True, index=True, nullable=True)

    phone = Column(String, index=True, nullable=True)  # en formato internacional, ej. 34600111222
    name = Column(String, nullable=True)
    initial_need = Column(Text, nullable=True)          # respuesta libre a "en que podemos ayudarte"
    application_or_fluid = Column(Text, nullable=True)  # aplicacion de la bomba / fluido a controlar
    email = Column(String, nullable=True)
    purchasing_email = Column(String, nullable=True)
    delivery_channel = Column(Enum(DeliveryChannel), nullable=True)

    state = Column(Enum(ConversationState), default=ConversationState.AWAITING_PHONE, nullable=False)
    whatsapp_opened = Column(Boolean, default=False)     # True en cuanto se manda la plantilla de apertura
    # True en cuanto el cliente escribe UNA VEZ por WhatsApp de verdad. Hasta
    # entonces, Meta no deja mandar texto libre (solo la plantilla inicial),
    # asi que Blas no intenta espejar las respuestas del widget web por
    # WhatsApp mientras esto sea False (ver services/conversation_flow.py).
    whatsapp_window_open = Column(Boolean, default=False)
    internal_notified = Column(Boolean, default=False)   # True en cuanto se avisa al equipo por email

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship("Message", back_populates="conversation", order_by="Message.created_at")


class Message(Base):
    __tablename__ = "messages"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(GUID(), ForeignKey("conversations.id"), nullable=False)

    direction = Column(String, nullable=False)   # "in" (del cliente) / "out" (de Blas)
    channel = Column(Enum(Channel), nullable=False)
    body = Column(Text, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="messages")
