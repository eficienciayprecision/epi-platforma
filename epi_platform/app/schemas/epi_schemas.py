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
    ENGRANAJES = "Engranajes"
    # NUEVO — bomba de piston neumatica (ARO 4-ball / AFX y similares): NO es
    # una neumatica de doble membrana aunque tambien funcione con aire
    # comprimido. Se detecto en agosto 2026 que 297 referencias ARO estaban
    # mal clasificadas como NEUMATICA_DOBLE_MEMBRANA cuando en realidad son
    # de piston — mecanicamente distintas (ver README).
    PISTON_NEUMATICO = "Pistón Neumático"


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

    # NUEVO (V7) — variables de proceso para el razonamiento de tecnologia de bomba.
    # Ninguna es obligatoria: si el cliente no las conoce, se asumen valores
    # conservadores (sin solidos, no abrasivo, no critico en continuidad de flujo).
    has_solids: bool = False
    max_particle_size_mm: Optional[float] = None
    is_abrasive: bool = False
    is_shear_sensitive: bool = False  # fluido delicado (p.ej. biologico, alimentario fragil)
    requires_continuous_flow: bool = False  # dosificacion/medicion de precision, sin pulsos


class TechnologyRecommendation(BaseModel):
    """Explicacion de por que una tecnologia de bomba encaja o no con el proceso descrito."""
    technology: PumpTechnology
    suitable: bool
    score: float = Field(..., ge=0.0, le=1.0)
    reasons: List[str] = []
    warnings: List[str] = []


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
    # NUEVO (V8): material en contacto con el fluido, para compatibilidad quimica.
    wetted_body_material: Optional[str] = None
    wetted_elastomer_material: Optional[str] = None
    # NUEVO (V9): enlace a la curva oficial del fabricante, cuando se localice.
    # De momento vacio para casi todo el catalogo -> se dibuja una curva
    # orientativa (aproximada, no exacta) a partir de caudal/presion maximos.
    curve_reference_url: Optional[str] = None
    # NUEVO — eficiencia real calculada (no la tipica por tecnologia), en %.
    # Solo para tecnologias de motor electrico con datos suficientes.
    real_efficiency_pct: Optional[float] = None


class ChemicalCompatibilityResult(BaseModel):
    """NUEVO (V8): resultado de comprobar si el fluido descrito es compatible
    con los materiales de la bomba seleccionada (cuerpo mojado y elastomero/
    junta). `compatible=None` significa que no hay dato de material suficiente
    para pronunciarse — no es un "si", hay que verificarlo a mano."""
    fluid_name: str
    body_material: Optional[str] = None
    elastomer_material: Optional[str] = None
    compatible: Optional[bool] = None
    warnings: List[str] = []


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
    parallel_pumps: bool = False


class PumpOnlyOffer(BaseModel):
    """NUEVO (agosto 2026) — oferta de SOLO la bomba (sin piping/instalacion),
    cuando el cliente responde "solo la bomba" a la pregunta inicial de la
    entrevista. A diferencia de SingleItemOffer (un elemento cualquiera
    identificado por foto), esta va siempre ligada a un calculo hidraulico
    real y muestra el razonamiento de por que se ha elegido esa tecnologia
    de bomba — antes ese razonamiento solo llegaba al email interno de EPi
    (InternalReport.technology_reasoning); aqui se traduce a texto y se
    manda tambien al cliente."""

    final_price_eur: float
    pump: SelectedPump
    fluid_name: str
    flow_m3h: float
    tdh_m: float
    velocity_ms: float
    # todas las tecnologias fisicamente aptas para esta aplicacion (no solo
    # la elegida), para que el cliente vea que otras opciones existen
    compatible_technologies: List[TechnologyRecommendation] = []
    # texto en prosa explicando por que la tecnologia elegida es la mejor
    # opcion para este caso, generado a partir de TechnologyRecommendation.reasons
    justification: str = ""
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
    # NUEVO (V7): por que se eligio esta tecnologia de bomba (y por que se
    # descartaron las demas), para que el ingeniero pueda revisarlo/corregirlo.
    technology_reasoning: List[TechnologyRecommendation] = []
    # NUEVO (V8): compatibilidad quimica fluido/material de la bomba elegida.
    chemical_compatibility: Optional[ChemicalCompatibilityResult] = None


class EPiFullSolution(BaseModel):
    profile_selected: InvestmentProfile
    hydraulics: HydraulicCalculationResponse
    selected_pump: SelectedPump
    materials_breakdown: MaterialsBreakdown
    commercial: CommercialBreakdown
    client_offer: ClientOffer
    internal_report: InternalReport
    # NUEVO (V7): por que EPi ha elegido esta tecnologia de bomba y no otra.
    technology_reasoning: List[TechnologyRecommendation] = []
    # NUEVO (V8): compatibilidad quimica fluido/material de la bomba elegida.
    chemical_compatibility: Optional[ChemicalCompatibilityResult] = None


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


class SparePartSearchResult(BaseModel):
    """NUEVO — resultado de buscar un repuesto por referencia."""
    referencia: str
    descripcion: str
    fabricante: str
    precio_eur: float


class SparePartQuoteRequest(BaseModel):
    referencia: str
    quantity: float = Field(default=1.0, gt=0)
    contact: Optional[ContactInfo] = None


class SparePartOffer(BaseModel):
    """NUEVO — oferta de UN repuesto (sin motor/bomba completa)."""
    referencia: str
    descripcion: str
    fabricante: str
    quantity: float
    unit_price_eur: float
    final_price_eur: float
    contact: Optional[ContactInfo] = None
    # NUEVO (agosto 2026): que pieza es y para que bomba/familia de bombas
    # sirve, cuando se ha podido identificar a partir del catalogo. None
    # cuando no hay evidencia suficiente en los datos de origen.
    tipo_componente: Optional[str] = None
    bomba_compatible: Optional[str] = None


class AdhesiveEquipmentItem(BaseModel):
    """NUEVO — un elemento de la oferta de equipo de adhesivo (con referencia real)."""
    elemento: str
    referencia: str
    fabricante: str
    precio_eur: float


class AdhesiveEquipmentOffer(BaseModel):
    """NUEVO — oferta de equipo de aplicacion de adhesivo 1K (pistola/automatismo +
    elevador de bidon), con referencia y precio de cada elemento."""
    application_type: str  # "manual" | "automatica"
    profile: str = "CALIDAD_PRECIO"
    drum_liters: Optional[float] = None
    hose_meters: Optional[float] = None
    items: List[AdhesiveEquipmentItem]
    final_price_eur: float
    contact: Optional[ContactInfo] = None


class AdhesiveFollowupRequest(BaseModel):
    """NUEVO — para 2K: no se oferta con precio, se recogen los datos y se
    avisa al cliente de que un ingeniero le contactara."""
    raw_answers: List[str]
    contact: Optional[ContactInfo] = None


class AdhesiveOfferRequest(BaseModel):
    """NUEVO — para 1K: datos ya recogidos por AdhesiveAgent, listos para
    generar la oferta de equipo con precio."""
    application_type: str  # "manual" | "automatica"
    profile: str = "CALIDAD_PRECIO"  # BARATA | CALIDAD_PRECIO | PREMIUM (bomba de piston)
    is_viscous: bool = False  # True -> bomba de clapetas (chop-check) en vez de bolas
    drum_liters: Optional[float] = None
    hose_meters: Optional[float] = None
    needs_photocell: bool = False
    needs_solenoid: bool = False
    contact: Optional[ContactInfo] = None


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
