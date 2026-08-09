"""Modelos SQLAlchemy: catalogo de bombas, usuarios internos y leads de clientes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, Boolean, Text, DateTime, JSON
from app.db.database import Base


class PumpModel(Base):
    __tablename__ = "pumps_catalog"

    id = Column(String, primary_key=True, index=True)
    brand = Column(String, index=True, nullable=False)
    model = Column(String, nullable=False)
    technology = Column(String, nullable=False)
    profile = Column(String, nullable=False, index=True)  # BARATA | CALIDAD_PRECIO | PREMIUM

    min_flow_m3h = Column(Float, nullable=False)
    max_flow_m3h = Column(Float, nullable=False)
    max_head_m = Column(Float, nullable=False)

    base_cost_eur = Column(Float, nullable=False)
    is_atex = Column(Boolean, default=False)
    description = Column(Text, default="")
    recommended_motor_kw = Column(Float, default=1.5)
    motor_voltage = Column(String, default="Trifasico 400V")
    match_score = Column(Float, default=0.8)
    # NUEVO (V8): material en contacto con el fluido, para compatibilidad quimica.
    wetted_body_material = Column(String, nullable=True)
    wetted_elastomer_material = Column(String, nullable=True)
    # NUEVO (V9): enlace a la curva oficial del fabricante, cuando se localice.
    curve_reference_url = Column(String, nullable=True)


class SparePartModel(Base):
    """NUEVO — catalogo de repuestos (sin motor/bomba completa), buscable por
    referencia exacta o parcial. El PVP ya es el precio final a mostrar al
    cliente (el margen de EPi viene del descuento de distribuidor sobre este
    mismo precio, no se le suma nada encima)."""
    __tablename__ = "spare_parts_catalog"

    referencia = Column(String, primary_key=True, index=True)
    descripcion = Column(Text, default="")
    fabricante = Column(String, default="", index=True)
    precio_eur = Column(Float, nullable=False)


class UserModel(Base):
    """Usuarios internos (staff): admin / engineer. Ya NO hay usuarios cliente:
    el cliente ahora se identifica solo con sus datos de contacto opcionales."""
    __tablename__ = "users"

    username = Column(String, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin | engineer
    hashed_password = Column(String, nullable=False)
    disabled = Column(Boolean, default=False)
    company = Column(String, default="Eficiencia y Precision Industrial S.L.")


class LeadModel(Base):
    """NUEVO — Registro de cada consulta/oferta generada, archivada bajo el
    contacto/empresa proporcionados (si los hay). No requiere login."""
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=lambda: uuid.uuid4().hex)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    contact_name = Column(String, nullable=True)
    company_name = Column(String, nullable=True, index=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True, index=True)

    client_id = Column(String, nullable=True, index=True)  # ref. al InternalReport.client_id
    final_price_eur = Column(Float, nullable=True)
    profile_selected = Column(String, nullable=True)

    email_sent = Column(Boolean, default=False)
    solution_snapshot = Column(JSON, nullable=True)  # copia de EPiFullSolution.model_dump()
