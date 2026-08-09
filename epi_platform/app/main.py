"""
EPi Platform Core API v1.2
Eficiencia y Precision Industrial S.L.

CAMBIO CLAVE: el cliente ya NO necesita usuario/contrasena para usar EPi.
Al empezar, opcionalmente aporta telefono, empresa y email. Si da el email,
la oferta se le envia automaticamente por correo y la consulta queda
archivada bajo esa empresa/contacto (tabla `leads`).
El login (JWT) se mantiene solo para el personal interno (admin/engineer),
que sigue siendo el unico que ve el Informe Interno con costes reales.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import (
    Token, User, UserCreate, UserRole,
    authenticate_user, create_access_token, hash_password,
    require_staff, require_admin,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.db.database import get_db, engine, Base
from app.db.models import PumpModel, UserModel, LeadModel
from app.schemas.epi_schemas import (
    InvestmentProfile, PumpTechnology, TechnologyRecommendation,
    HydraulicCalculationRequest, HydraulicCalculationResponse,
    SelectedPump, MaterialsBreakdown, EPiFullSolution, ContactInfo,
    ObjectIdentificationResult, ItemQuoteRequest, SingleItemSolution,
)
from app.engine.hydraulics import HydraulicEngine
from app.engine.commercial import CommercialEngine
from app.engine.energy import EnergyOptimizer
from app.engine.pump_technology import PumpTechnologyAdvisor
from app.engine.chemical_compatibility import ChemicalCompatibilityAdvisor
from app.agents.interview import InterviewAgent
from app.agents.efficiency import EfficiencyAdvisorAgent
from app.agents.adhesive import AdhesiveAgent
from app.services.pdf_generator import (
    generate_client_offer_pdf, generate_internal_report_pdf,
    generate_single_item_offer_pdf, generate_single_item_internal_pdf,
)
from app.services.scraper import PriceScraper
from app.services.email_service import send_offer_email
from app.services.vision_service import identify_object_from_image

Base.metadata.create_all(bind=engine)

# NUEVO (fix agosto 2026): antes el catalogo de bombas solo se cargaba si
# alguien ejecutaba "python -m app.db.seed" a mano (via Shell de Render).
# El plan gratuito de Render no tiene Shell, asi que nunca se llegaba a
# cargar el catalogo real de 1.509 bombas — la app se quedaba con las 6 de
# ejemplo (o vacia, si la base de datos es efimera). Se ejecuta aqui, en
# cada arranque: es seguro y rapido llamarlo siempre porque internamente ya
# comprueba si el catalogo esta cargado y no hace nada si ya lo esta.
try:
    from app.db.seed import seed as _seed_database
    _seed_database()
except Exception as _seed_error:  # nunca debe impedir que la app arranque
    print(f"AVISO: no se pudo cargar el catalogo de bombas al arrancar: {_seed_error}")

app = FastAPI(
    title="EPi Engine API",
    version="1.8.1",
    description="Asistente IA para mecanica de fluidos — EPI S.L. Bilbao",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
commercial_engine = CommercialEngine(labor_engineering_eur=1800.0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pump_row_to_selected(row: PumpModel) -> SelectedPump:
    tech_map = {
        "Centrifuga con cierre mecanico": PumpTechnology.CENTRIFUGA_MECANICO,
        "Centrifuga de Acoplamiento Magnetico": PumpTechnology.CENTRIFUGA_MAGNETICO,
        "Neumatica de Doble Membrana": PumpTechnology.NEUMATICA_DOBLE_MEMBRANA,
        "Peristaltica": PumpTechnology.PERISTALTICA,
        "Tornillo Helicoidal": PumpTechnology.TORNILLO_HELICOIDAL,
        "Engranajes": PumpTechnology.ENGRANAJES,
    }
    tech = tech_map.get(row.technology, PumpTechnology.CENTRIFUGA_MECANICO)
    try:
        profile = InvestmentProfile(row.profile)
    except ValueError:
        profile = InvestmentProfile.CALIDAD_PRECIO
    return SelectedPump(
        id=row.id, brand=row.brand, model=row.model,
        technology=tech, profile=profile,
        min_flow_m3h=row.min_flow_m3h, max_flow_m3h=row.max_flow_m3h,
        max_head_m=row.max_head_m, is_atex=row.is_atex,
        base_cost_eur=row.base_cost_eur, description=row.description or "",
        recommended_motor_kw=row.recommended_motor_kw or 1.5,
        motor_voltage=row.motor_voltage or "Trifasico 400V",
        match_score=row.match_score or 0.8,
        wetted_body_material=row.wetted_body_material,
        wetted_elastomer_material=row.wetted_elastomer_material,
        curve_reference_url=row.curve_reference_url,
    )


def _query_technology(
    db: Session, flow: float, head: float, profile: InvestmentProfile,
    atex: bool, technology: PumpTechnology, relax_profile: bool = False,
) -> List[PumpModel]:
    q = db.query(PumpModel).filter(
        PumpModel.technology == technology.value,
        PumpModel.min_flow_m3h <= flow,
        PumpModel.max_flow_m3h >= flow,
        PumpModel.max_head_m >= head,
    )
    if not relax_profile:
        q = q.filter(PumpModel.profile == profile.value)
    if atex:
        q = q.filter(PumpModel.is_atex == True)  # noqa: E712
    return q.all()


def select_from_db(
    db: Session, flow: float, head: float, profile: InvestmentProfile, atex: bool = False,
    hydraulics_req: Optional[HydraulicCalculationRequest] = None,
) -> tuple[Optional[SelectedPump], List[TechnologyRecommendation]]:
    """NUEVO (V7): ya no busca solo por caudal/altura/perfil — primero decide
    que tecnologia(s) son fisicamente aptas para el proceso descrito
    (solidos, abrasividad, necesidad de flujo continuo...) usando
    PumpTechnologyAdvisor, y solo dentro de esas tecnologias aplica el
    filtro de caudal/altura/perfil de siempre. Se prueban las tecnologias
    aptas en orden de puntuacion; si la mas adecuada no tiene stock en ese
    caudal/altura/perfil, se prueba la siguiente antes de rendirse.
    Devuelve tambien el razonamiento completo (aptas y no aptas) para que
    el informe pueda explicar la decision.

    NUEVO (V8): dentro de cada tecnologia, si se conoce el fluido y hay mas
    de una bomba candidata, se descartan primero las que tengan un material
    de cuerpo o elastomero conocido como quimicamente incompatible con ese
    fluido — salvo que TODAS las candidatas de esa tecnologia lo sean, en
    cuyo caso se sigue eligiendo la de mejor match_score (major devolver una
    bomba con aviso de compatibilidad que ninguna bomba)."""

    hyd_req = hydraulics_req or HydraulicCalculationRequest(
        flow_m3h=flow, diameter_mm=100.0, length_m=10.0,
    )
    reasoning = PumpTechnologyAdvisor.evaluate(hyd_req, profile)
    ranked_allowed = [r.technology for r in reasoning if r.suitable]
    if not ranked_allowed:
        ranked_allowed = [r.technology for r in reasoning]

    bad_body, bad_elastomer = ChemicalCompatibilityAdvisor.bad_materials_for(hyd_req.fluid_name)

    def _best(rows: List[PumpModel]) -> PumpModel:
        if bad_body or bad_elastomer:
            compatible_rows = [
                r for r in rows
                if r.wetted_body_material not in bad_body
                and r.wetted_elastomer_material not in bad_elastomer
            ]
            if compatible_rows:
                rows = compatible_rows
        return max(rows, key=lambda r: r.match_score or 0)

    for tech in ranked_allowed:
        rows = _query_technology(db, flow, head, profile, atex, tech)
        if rows:
            return pump_row_to_selected(_best(rows)), reasoning

    # Ninguna bomba en el perfil de inversion pedido: relajamos el perfil
    # (pero NUNCA la tecnologia, que es una restriccion fisica, no de precio)
    for tech in ranked_allowed:
        rows = _query_technology(db, flow, head, profile, atex, tech, relax_profile=True)
        if rows:
            return pump_row_to_selected(_best(rows)), reasoning

    return None, reasoning


def default_materials(diameter_mm: float, length_m: float, use_scraper: bool = True) -> MaterialsBreakdown:
    scraper = PriceScraper(enable_web=use_scraper)
    return scraper.build_materials_for_line(diameter_mm, length_m, commercial_engine)


def compute_full_solution(req: "FullSolutionRequest", db: Session) -> EPiFullSolution:
    hyd = HydraulicEngine(req.hydraulics_input).compute()
    pump, tech_reasoning = select_from_db(
        db, hyd.flow_m3h, hyd.total_dynamic_head_m, req.profile, req.is_atex_required,
        hydraulics_req=req.hydraulics_input,
    )
    if not pump:
        raise HTTPException(
            status_code=404,
            detail=f"No hay bomba para perfil {req.profile.value} "
                   f"Q={hyd.flow_m3h} TDH={hyd.total_dynamic_head_m} "
                   f"con una tecnologia apta para el proceso descrito.",
        )
    # El caudalimetro hidraulico solo aplica a bombas con motor electrico:
    # las neumaticas (AODD) no llevan motor electrico, se alimentan de aire.
    if pump.technology != PumpTechnology.NEUMATICA_DOBLE_MEMBRANA:
        pump = pump.model_copy(update={"recommended_motor_kw": hyd.recommended_motor_kw})

    # NUEVO (V8): compatibilidad quimica del fluido con el material de la bomba elegida.
    chem_check = ChemicalCompatibilityAdvisor.check(
        fluid_name=req.hydraulics_input.fluid_name,
        body_material=pump.wetted_body_material,
        elastomer_material=pump.wetted_elastomer_material,
    )

    if req.custom_materials:
        lines = [commercial_engine.build_material_line(**m) for m in req.custom_materials]
        materials = commercial_engine.build_materials_breakdown(lines)
    else:
        materials = default_materials(
            req.hydraulics_input.diameter_mm,
            req.hydraulics_input.length_m,
            use_scraper=req.use_scraper,
        )

    client_id = req.client_id or f"REF-IND-BILBAO-{uuid.uuid4().hex[:4].upper()}"
    return commercial_engine.build_full_solution(
        profile=req.profile, pump=pump, materials=materials, hydraulics=hyd,
        client_id=client_id, labor_engineering_eur=req.labor_engineering_eur,
        network_status=req.network_status, contact=req.contact,
        technology_reasoning=tech_reasoning,
        chemical_compatibility=chem_check,
    )


def save_lead(db: Session, solution: EPiFullSolution, contact: Optional[ContactInfo]) -> LeadModel:
    lead = LeadModel(
        contact_name=contact.contact_name if contact else None,
        company_name=contact.company_name if contact else None,
        phone=contact.phone if contact else None,
        email=contact.email if contact else None,
        client_id=solution.internal_report.client_id,
        final_price_eur=solution.commercial.final_client_price_eur,
        profile_selected=solution.profile_selected.value,
        solution_snapshot=solution.model_dump(mode="json"),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    history: List[dict] = []


class FullSolutionRequest(BaseModel):
    hydraulics_input: HydraulicCalculationRequest
    profile: InvestmentProfile = InvestmentProfile.CALIDAD_PRECIO
    is_atex_required: bool = False
    client_id: Optional[str] = None
    labor_engineering_eur: Optional[float] = None
    network_status: str = "Tuberias Soldadas (Sin Parada)"
    custom_materials: Optional[List[dict]] = None
    use_scraper: bool = True
    # NUEVO — sustituye al login del cliente. Nada aqui es obligatorio.
    contact: Optional[ContactInfo] = None


class EnergyRequest(BaseModel):
    flow_m3h: float = Field(..., gt=0)
    head_m: float = Field(..., gt=0)
    hours_per_year: int = 8000
    energy_cost_kwh: float = 0.15
    current_eff: float = 0.60
    new_eff_with_vfd: float = 0.78
    vfd_cost_eur: float = 2500.0


class PumpSelectRequest(BaseModel):
    flow_m3h: float = Field(..., gt=0)
    total_head_m: float = Field(..., gt=0)
    is_atex_required: bool = False
    # NUEVO (V7) — mismas variables de proceso que en el calculo hidraulico,
    # para que la seleccion manual (uso interno) tambien razone tecnologia.
    has_solids: bool = False
    is_abrasive: bool = False
    is_shear_sensitive: bool = False
    requires_continuous_flow: bool = False
    # NUEVO (V8) — para poder comprobar compatibilidad quimica tambien aqui.
    fluid_name: str = "Agua"


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "system": "EPi Platform", "version": "1.8.1"}


@app.get("/", tags=["System"])
def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"message": "EPi API", "docs": "/docs", "ui": "/ui/"}


# ---------------------------------------------------------------------------
# Auth — SOLO personal interno
# ---------------------------------------------------------------------------

@app.post("/api/v1/auth/login", response_model=Token, tags=["Auth interno"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Usuario o contrasena incorrectos",
                            headers={"WWW-Authenticate": "Bearer"})
    token = create_access_token(
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(
        access_token=token, expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=UserRole(user.role), username=user.username,
    )


@app.post("/api/v1/auth/register", response_model=User, tags=["Auth interno"])
def register(payload: UserCreate, db: Session = Depends(get_db),
             _: User = Depends(require_admin)):
    if db.query(UserModel).filter(UserModel.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Usuario ya existe")
    row = UserModel(
        username=payload.username, full_name=payload.full_name,
        role=payload.role.value, hashed_password=hash_password(payload.password),
    )
    db.add(row)
    db.commit()
    return User(username=row.username, full_name=row.full_name, role=payload.role)


# ---------------------------------------------------------------------------
# Interview — PUBLICA, sin login
# ---------------------------------------------------------------------------

@app.post("/api/v1/interview/chat", tags=["Cliente — Entrevista"])
def interview_chat(request: ChatRequest):
    """Conversacion adaptativa, abierta a cualquier visitante de la web.

    Rama del menu inicial: "Mejorar mi instalacion" (dimensionamiento nuevo).
    """
    return InterviewAgent.process_message(request.message, request.history)


@app.post("/api/v1/efficiency/advise", tags=["Cliente — Eficiencia de planta"])
def efficiency_advise(request: ChatRequest):
    """Rama del menu inicial: "Mejorar la eficiencia de mi planta".

    El cliente describe su instalacion existente en texto libre; EPi
    identifica oportunidades de mejora de eficiencia (rendimiento de cada
    bomba, reduccion de perdidas de carga) y su traduccion en ahorro
    energetico. No dimensiona una bomba nueva: asesora sobre una existente.
    """
    return EfficiencyAdvisorAgent.process_message(request.message, request.history)


@app.post("/api/v1/adhesive/chat", tags=["Cliente — Instalacion de adhesivo"])
def adhesive_chat(request: ChatRequest):
    """Rama del menu inicial: "Tengo una instalacion de adhesivo que deseo mejorar".

    Primera pregunta siempre fija: adhesivo de un componente (1K) o de dos
    componentes (2K), que determina el resto del guion de la entrevista.
    """
    return AdhesiveAgent.process_message(request.message, request.history)


# ---------------------------------------------------------------------------
# Hidraulica / Bombas — uso interno (calculo manual, catalogo)
# ---------------------------------------------------------------------------

@app.post("/api/v1/hydraulics/calculate", response_model=HydraulicCalculationResponse,
          tags=["Interno — Hidraulica"])
def calculate(request: HydraulicCalculationRequest, _: User = Depends(require_staff)):
    try:
        return HydraulicEngine(request).compute()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/pumps/select", tags=["Interno — Seleccion"])
def select_pumps(request: PumpSelectRequest, db: Session = Depends(get_db),
                 _: User = Depends(require_staff)):
    hyd_req = HydraulicCalculationRequest(
        flow_m3h=request.flow_m3h, diameter_mm=100.0, length_m=10.0,
        fluid_name=request.fluid_name,
        has_solids=request.has_solids, is_abrasive=request.is_abrasive,
        is_shear_sensitive=request.is_shear_sensitive,
        requires_continuous_flow=request.requires_continuous_flow,
    )
    result = {}
    reasoning = None
    for profile in InvestmentProfile:
        pump, reasoning = select_from_db(
            db, request.flow_m3h, request.total_head_m, profile,
            request.is_atex_required, hydraulics_req=hyd_req,
        )
        if pump:
            chem = ChemicalCompatibilityAdvisor.check(
                fluid_name=request.fluid_name,
                body_material=pump.wetted_body_material,
                elastomer_material=pump.wetted_elastomer_material,
            )
            result[profile.value] = {
                "pump": pump.model_dump(),
                "chemical_compatibility": chem.model_dump(),
            }
    return {
        "pumps_by_profile": result,
        "technology_reasoning": [r.model_dump() for r in (reasoning or [])],
    }


# ---------------------------------------------------------------------------
# Solucion completa + PDFs + email — PUBLICA, sin login
# ---------------------------------------------------------------------------

@app.post("/api/v1/solution/oneshot", tags=["Cliente — Oferta"])
def solution_oneshot(request: FullSolutionRequest, db: Session = Depends(get_db)):
    """Hidraulica + bomba + margenes + 2 PDFs en una llamada.
    Abierta a cualquier visitante. Si `contact.email` viene informado:
      - se guarda la consulta como lead bajo esa empresa/contacto
      - se envia automaticamente la Oferta Cliente en PDF a ese email
    """
    solution = compute_full_solution(request, db)
    cid = solution.internal_report.client_id
    client_path = OUTPUT_DIR / f"Oferta_Cliente_{cid}.pdf"
    internal_path = OUTPUT_DIR / f"Informe_Interno_{cid}.pdf"
    generate_client_offer_pdf(solution.client_offer, str(client_path))
    generate_internal_report_pdf(solution.internal_report, str(internal_path))

    lead = save_lead(db, solution, request.contact)

    email_sent = False
    if request.contact and request.contact.email:
        email_sent = send_offer_email(
            to_email=request.contact.email,
            contact_name=request.contact.contact_name,
            company_name=request.contact.company_name,
            pdf_path=str(client_path),
            final_price_eur=solution.commercial.final_client_price_eur,
        )
        if email_sent:
            lead.email_sent = True
            db.commit()

    return {
        "solution": solution.model_dump(),
        "client_pdf": str(client_path),
        "internal_pdf": str(internal_path),
        "lead_id": lead.id,
        "email_sent": email_sent,
    }


@app.post("/api/v1/report/client-pdf", tags=["Cliente — Oferta"])
def client_pdf(solution: EPiFullSolution):
    """Descarga directa de la oferta cliente. Publica."""
    path = OUTPUT_DIR / f"Oferta_Cliente_{solution.internal_report.client_id}.pdf"
    generate_client_offer_pdf(solution.client_offer, str(path))
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@app.post("/api/v1/report/internal-pdf", tags=["Interno — Documentos"])
def internal_pdf(solution: EPiFullSolution, _: User = Depends(require_staff)):
    """Solo personal interno. El cliente nunca ve este documento."""
    path = OUTPUT_DIR / f"Informe_Interno_{solution.internal_report.client_id}.pdf"
    generate_internal_report_pdf(solution.internal_report, str(path))
    return FileResponse(path, filename=path.name, media_type="application/pdf")


# ---------------------------------------------------------------------------
# Leads — SOLO personal interno
# ---------------------------------------------------------------------------

@app.get("/api/v1/leads", tags=["Interno — Leads"])
def list_leads(db: Session = Depends(get_db), _: User = Depends(require_staff)):
    """Lista de consultas/ofertas archivadas por empresa/contacto."""
    rows = db.query(LeadModel).order_by(LeadModel.created_at.desc()).all()
    return [
        {
            "id": r.id, "created_at": r.created_at, "contact_name": r.contact_name,
            "company_name": r.company_name, "phone": r.phone, "email": r.email,
            "client_id": r.client_id, "final_price_eur": r.final_price_eur,
            "profile_selected": r.profile_selected, "email_sent": r.email_sent,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Energia / Scraping — uso interno
# ---------------------------------------------------------------------------

@app.post("/api/v1/energy/optimize", tags=["Interno — Energia"])
def energy_optimize(request: EnergyRequest, _: User = Depends(require_staff)):
    opt = EnergyOptimizer(
        flow_m3h=request.flow_m3h, head_m=request.head_m,
        hours_per_year=request.hours_per_year, energy_cost_kwh=request.energy_cost_kwh,
    )
    return opt.compare_vfd_savings(
        current_eff=request.current_eff, new_eff_with_vfd=request.new_eff_with_vfd,
        vfd_cost_eur=request.vfd_cost_eur,
    )


@app.post("/api/v1/scraper/preview", tags=["Interno — Scraping"])
def scraper_preview(
    diameter_mm: float = 50.0, length_m: float = 25.0, enable_web: bool = True,
    _: User = Depends(require_staff),
):
    scraper = PriceScraper(enable_web=enable_web)
    materials = scraper.build_materials_for_line(diameter_mm, length_m, commercial_engine)
    return materials.model_dump()


# ---------------------------------------------------------------------------
# Rediseño de instalación a partir de una foto — CONCEPT STUB
# ---------------------------------------------------------------------------
# NO calcula medidas reales todavia. Aceptar la foto y devolver una respuesta
# de ejemplo permite validar el flujo de usuario (subida de foto + objeto de
# referencia) mientras se decide y desarrolla el modulo real de vision por
# computador (calibracion de escala a partir de un objeto conocido, deteccion
# de tuberia/codos/valvulas, y generacion de una propuesta de rediseño). Ver
# hoja de ruta, Fase 3.

@app.post("/api/v1/photo/redesign", tags=["Cliente — Rediseño por foto (beta)"])
async def photo_redesign(
    photo: UploadFile = File(...),
    reference_object: str = Form(...),
    reference_length_mm: float = Form(...),
):
    """Rama del menú inicial: "Rediseñar mi instalación a partir de una foto".

    CONCEPT STUB: valida el flujo de subida de foto y objeto de referencia,
    pero todavía NO extrae medidas reales de la imagen ni genera un rediseño
    real. Devuelve una respuesta de ejemplo, claramente marcada como tal, a
    la espera de desarrollar el módulo de visión por computador (detección de
    escala, tramos de tubería, codos y válvulas).
    """
    contents = await photo.read()
    size_kb = round(len(contents) / 1024, 1)
    return {
        "status": "concept_preview",
        "message": (
            f"Foto recibida ({photo.filename}, {size_kb} KB) junto con el objeto de "
            f"referencia indicado ('{reference_object}', {reference_length_mm} mm). "
            "Esta función está en fase de concepto: todavía no mide la instalación "
            "real ni genera un rediseño a partir de la imagen. Cuando esté "
            "desarrollada, EPi calibrará la escala de la foto usando el objeto de "
            "referencia, identificará los tramos de tubería, codos y válvulas "
            "visibles, y propondrá qué añadir, mover o eliminar para reducir la "
            "pérdida de carga de la instalación."
        ),
        "example_redesign_preview": {
            "detected_elements": "[pendiente de desarrollo]",
            "suggested_changes": "[pendiente de desarrollo]",
        },
    }


# ---------------------------------------------------------------------------
# Identificar UN elemento suelto por foto y ofertar solo ese elemento
# — PUBLICA, sin login — DISTINTO del stub de rediseño de instalacion completa
# ---------------------------------------------------------------------------
# Flujo: 1) el cliente sube una foto de un elemento suelto (no de toda la
# instalacion) -> 2) EPi lo identifica (Vision API por debajo, sin mostrar
# la marca) y pide confirmacion -> 3) si el cliente confirma y quiere
# oferta, se busca el precio (catalogo interno / scraper web) y se genera
# la oferta igual que el resto de EPi (margenes +40%/+38%, PDF cliente +
# PDF interno, envio por email si hay contacto, archivado como lead).

@app.post("/api/v1/photo/identify-item", response_model=ObjectIdentificationResult,
          tags=["Cliente — Identificar elemento por foto"])
async def photo_identify_item(photo: UploadFile = File(...)):
    """Sube una foto de UN elemento suelto (válvula, bomba, sensor...).
    Devuelve la identificación propuesta; el cliente debe confirmarla o
    corregirla antes de pedir oferta (ver /api/v1/photo/quote-item)."""
    contents = await photo.read()
    return identify_object_from_image(contents)


@app.post("/api/v1/photo/quote-item", tags=["Cliente — Identificar elemento por foto"])
def photo_quote_item(request: ItemQuoteRequest, db: Session = Depends(get_db)):
    """El cliente ya confirmó (o corrigió) el elemento y quiere oferta solo
    de él. Busca precio en catálogo interno; si no lo encuentra, queda
    preparado para la búsqueda web real (mismo mecanismo que el resto de
    componentes). Genera los 2 PDFs, envía email si hay contacto y archiva
    la consulta como lead, igual que el resto de ofertas de EPi."""
    scraper = PriceScraper(enable_web=request.use_scraper)
    found = scraper.lookup_generic_item(request.item_name)

    solution: SingleItemSolution = commercial_engine.build_single_item_solution(
        request=request,
        supplier=found["supplier"],
        unit_cost_real_eur=found["unit_cost"],
        unit=found["unit"],
    )

    cid = solution.internal_report.client_id
    client_path = OUTPUT_DIR / f"Oferta_Elemento_{cid}.pdf"
    internal_path = OUTPUT_DIR / f"Informe_Interno_Elemento_{cid}.pdf"
    generate_single_item_offer_pdf(solution.client_offer, str(client_path))
    generate_single_item_internal_pdf(solution.internal_report, str(internal_path))

    lead = LeadModel(
        contact_name=request.contact.contact_name if request.contact else None,
        company_name=request.contact.company_name if request.contact else None,
        phone=request.contact.phone if request.contact else None,
        email=request.contact.email if request.contact else None,
        client_id=cid,
        final_price_eur=solution.client_offer.final_price_eur,
        profile_selected="ELEMENTO_UNICO",
        solution_snapshot=solution.model_dump(mode="json"),
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    email_sent = False
    if request.contact and request.contact.email:
        email_sent = send_offer_email(
            to_email=request.contact.email,
            contact_name=request.contact.contact_name,
            company_name=request.contact.company_name,
            pdf_path=str(client_path),
            final_price_eur=solution.client_offer.final_price_eur,
        )
        if email_sent:
            lead.email_sent = True
            db.commit()

    return {
        "solution": solution.model_dump(),
        "item_matched_in_catalog": found["matched"],
        "client_pdf": str(client_path),
        "internal_pdf": str(internal_path),
        "lead_id": lead.id,
        "email_sent": email_sent,
    }
