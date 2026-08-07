"""Esquemas Pydantic del proyecto EPi — Eficiencia y Precision Industrial S.L."""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Enumerados
# ---------------------------------------------------------------------------

class InvestmentProfile(str, Enum):
    BARATA = "BARATA"
    CALIDAD_PRECIO = "CALIDAD_PRECIO"
    PREMIUM = "PREMIUM"


class PumpTechnology(str, Enum):
    CENTRIFUGA_MECANICO = "Centrifuga con cierre mecanico"
    CENTRIFUGA_MAGNETICO = "Centrifuga de Acoplamiento Magnetico"
    NEUMATICA_DOBLE_MEMBRANA = "Neumatica de Doble Membrana"
    PERISTALTICA = "Peristaltica"
    TORNILLO_HELICOIDAL = "Tornillo Helicoidal"


# ---------------------------------------------------------------------------
# NUEVO: Datos de contacto (sustituye al login obligatorio)
# ---------------------------------------------------------------------------

class ContactInfo(BaseModel):
    """Datos de contacto del cliente. Ninguno es obligatorio para poder
    empezar a usar EPi, pero si se aporta el email, la oferta se envia
    automaticamente a esa direccion y queda archivada bajo esa empresa/contacto."""

    contact_name: Optional[str] = Field(default=None, max_length=150)
    company_name: Optional[str] = Field(default=None, max_length=150)
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[EmailStr] = None


# ---------------------------------------------------------------------------
# Hidraulica
# ---------------------------------------------------------------------------

class HydraulicCalculationRequest(BaseModel):
    flow_m3h: float = Field(..., gt=0)
    diameter_mm: float = Field(..., gt=0)
    length_m: float = Field(..., gt=0)
    static_head_m: float = 0.0
    density_kg_m3: float = 1000.0
    viscosity_cp: float = 1.0
    fluid_name: str = "Agua"
    roughness_mm: float = 0.045  # acero inoxidable estandar
    k_accessories: float = 5.0
    npsh_available_m: Optional[float] = None


class HydraulicCalculationResponse(BaseModel):
    flow_m3h: float
    fluid_name: str
    diameter_mm: float
    velocity_ms: float
    reynolds: float
    flow_regime: str
    friction_factor: float
    friction_head_loss_m: float
    singular_head_loss_m: float
    total_head_loss_m: float
    total_dynamic_head_m: float
    hydraulic_power_kw: float
    shaft_power_kw: float
    recommended_motor_kw: float
    npsh_available_m: Optional[float] = None
    npsh_required_max_m: Optional[float] = None
    velocity_warning: Optional[str] = None


# ---------------------------------------------------------------------------
# Bombas
# ---------------------------------------------------------------------------

class SelectedPump(BaseModel):
    id: str
    brand: str
    model: str
    technology: PumpTechnology
    profile: InvestmentProfile
    min_flow_m3h: float
    max_flow_m3h: float
    max_head_m: float
    is_atex: bool = False
    base_cost_eur: float
    description: str = ""
    recommended_motor_kw: float = 1.5
    motor_voltage: str = "Trifasico 400V"
    match_score: float = 0.8


# ---------------------------------------------------------------------------
# Materiales
# ---------------------------------------------------------------------------

class MaterialLine(BaseModel):
    component: str
    supplier: str
    quantity: float
    unit: str
    unit_cost_real_eur: float
    total_cost_real_eur: float
    margin_pct: float
    pvp_with_margin_eur: float


class MaterialsBreakdown(BaseModel):
    lines: List[MaterialLine]
    total_cost_real_eur: float
    total_pvp_with_40_eur: float


# ---------------------------------------------------------------------------
# Comercial
# ---------------------------------------------------------------------------

class CommercialBreakdown(BaseModel):
    pump_base_cost_eur: float
    materials_pvp_40_eur: float
    labor_engineering_eur: float
    subtotal_commercial_eur: float
    contingency_pct: float
    contingency_amount_eur: float
    final_client_price_eur: float
    estimated_gross_profit_eur: float


class ClientOfferMaterial(BaseModel):
    element: str
    specification: str
    quantity_display: str


class ClientOffer(BaseModel):
    final_price_eur: float
    pump: SelectedPump
    materials: List[ClientOfferMaterial]
    fluid_name: str
    flow_m3h: float
    total_head_loss_m: float
    tdh_m: float
    velocity_ms: float
    npsh_available_m: Optional[float] = None
    # NUEVO: a quien pertenece esta oferta
    contact: Optional[ContactInfo] = None


class InternalReport(BaseModel):
    consultation_date: date
    client_id: str
    network_status: str
    hydraulics: HydraulicCalculationResponse
    materials_breakdown: MaterialsBreakdown
    commercial: CommercialBreakdown
    selected_pump: SelectedPump
    engineer_instructions: str
    # NUEVO
    contact: Optional[ContactInfo] = None


class EPiFullSolution(BaseModel):
    profile_selected: InvestmentProfile
    hydraulics: HydraulicCalculationResponse
    selected_pump: SelectedPump
    materials_breakdown: MaterialsBreakdown
    commercial: CommercialBreakdown
    client_offer: ClientOffer
    internal_report: InternalReport


# ---------------------------------------------------------------------------
# NUEVO: Identificacion de un elemento suelto por foto + oferta individual
# ---------------------------------------------------------------------------

class ObjectIdentificationResult(BaseModel):
    """Resultado de analizar una foto de un elemento suelto (no una instalacion
    completa). El cliente debe confirmar o corregir antes de pedir oferta."""

    detected_label: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    suggestion_text: str
    source: str = "vision_api"  # "vision_api" | "fallback_sin_configurar"


class ItemQuoteRequest(BaseModel):
    """Elemento ya confirmado (o corregido) por el cliente, listo para ofertar."""

    item_name: str = Field(..., max_length=200)
    quantity: float = Field(default=1.0, gt=0)
    use_scraper: bool = True
    contact: Optional[ContactInfo] = None


class SingleItemOffer(BaseModel):
    """Oferta comercial de UN unico elemento (no una instalacion completa)."""

    item_name: str
    supplier: str
    quantity: float
    unit: str
    final_price_eur: float
    contact: Optional[ContactInfo] = None


class SingleItemInternalReport(BaseModel):
    consultation_date: date
    client_id: str
    item_line: MaterialLine
    commercial: CommercialBreakdown
    contact: Optional[ContactInfo] = None


class SingleItemSolution(BaseModel):
    client_offer: SingleItemOffer
    internal_report: SingleItemInternalReport
