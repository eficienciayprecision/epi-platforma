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

import os
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
from app.db.models import PumpModel, UserModel, LeadModel, SparePartModel
from app.schemas.epi_schemas import (
    InvestmentProfile, PumpTechnology, TechnologyRecommendation,
    HydraulicCalculationRequest, HydraulicCalculationResponse,
    SelectedPump, MaterialsBreakdown, EPiFullSolution, ContactInfo,
    ObjectIdentificationResult, ItemQuoteRequest, SingleItemSolution,
    SparePartQuoteRequest, SparePartOffer,
    AdhesiveFollowupRequest, AdhesiveOfferRequest, AdhesiveEquipmentOffer, AdhesiveEquipmentItem,
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
    generate_spare_part_offer_pdf, generate_adhesive_equipment_offer_pdf,
)
from app.services.scraper import PriceScraper
from app.services.email_service import send_offer_email, send_internal_report_email, send_adhesive_followup_email
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
    version="1.11.0",
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
        "Pistón Neumático": PumpTechnology.PISTON_NEUMATICO,
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
        real_efficiency_pct=row.real_efficiency_pct,
    )


def _query_technology(
    db: Session, flow: float, head: float, profile: InvestmentProfile,
    atex: bool, technology: PumpTechnology, relax_profile: bool = False,
    density_kg_m3: float = 1000.0,
) -> List[PumpModel]:
    # NUEVO — el catalogo de bombas esta baremado en agua (densidad
    # 1000 kg/m3). En una CENTRIFUGA, a potencia de motor fija, el caudal
    # real que puede dar con un fluido mas denso que el agua es MENOR (hace
    # falta mas potencia para mover la misma cantidad de fluido), y con uno
    # mas ligero es MAYOR — aproximacion estandar: caudal_real ~ caudal_agua
    # x (1000/densidad_fluido). En vez de tocar cada fila del catalogo, se
    # convierte el caudal pedido por el cliente a su "equivalente en agua"
    # antes de comparar contra los rangos de caudal del catalogo (mismo
    # resultado, mas simple). En bombas de desplazamiento positivo
    # (engranajes, tornillo, peristaltica, neumaticas, piston) el caudal NO
    # depende de la densidad -- ahi no se aplica ninguna correccion.
    query_flow = flow
    if technology in (PumpTechnology.CENTRIFUGA_MECANICO, PumpTechnology.CENTRIFUGA_MAGNETICO):
        query_flow = flow * (density_kg_m3 / 1000.0)

    q = db.query(PumpModel).filter(
        PumpModel.technology == technology.value,
        PumpModel.min_flow_m3h <= query_flow,
        PumpModel.max_flow_m3h >= query_flow,
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

    # NUEVO — en el perfil BARATA, la neumatica de doble membrana es casi
    # siempre la de menor coste de compra (aunque no la de mejor eficiencia,
    # que es lo que usa PumpTechnologyAdvisor para puntuar). Si es fisicamente
    # apta para el proceso, se prueba SIEMPRE la primera en el perfil barato,
    # por delante de tecnologias con mejor puntuacion de eficiencia.
    if profile == InvestmentProfile.BARATA and PumpTechnology.NEUMATICA_DOBLE_MEMBRANA in ranked_allowed:
        ranked_allowed = [PumpTechnology.NEUMATICA_DOBLE_MEMBRANA] + [
            t for t in ranked_allowed if t != PumpTechnology.NEUMATICA_DOBLE_MEMBRANA
        ]

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
        rows = _query_technology(db, flow, head, profile, atex, tech, density_kg_m3=hyd_req.density_kg_m3)
        if rows:
            return pump_row_to_selected(_best(rows)), reasoning

    # Ninguna bomba en el perfil de inversion pedido: relajamos el perfil
    # (pero NUNCA la tecnologia, que es una restriccion fisica, no de precio)
    for tech in ranked_allowed:
        rows = _query_technology(db, flow, head, profile, atex, tech, relax_profile=True, density_kg_m3=hyd_req.density_kg_m3)
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
    if pump.technology not in (PumpTechnology.NEUMATICA_DOBLE_MEMBRANA, PumpTechnology.PISTON_NEUMATICO):
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
    return {"status": "ok", "system": "EPi Platform", "version": "1.11.0"}


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

    # NUEVO — copia del informe TECNICO interno (de donde ha sacado cada
    # componente, razonamiento de tecnologia, compatibilidad quimica) a la
    # direccion interna, en cada presupuesto generado (independientemente
    # de si el cliente dejo su email o no).
    internal_email_sent = send_internal_report_email(
        to_email=os.getenv("EPI_INTERNAL_REPORT_EMAIL", "epi@eficienciayprecisionindustrial.com"),
        client_id=cid,
        pdf_path=str(internal_path),
        final_price_eur=solution.commercial.final_client_price_eur,
    )

    return {
        "solution": solution.model_dump(),
        "client_pdf": str(client_path),
        "internal_pdf": str(internal_path),
        "lead_id": lead.id,
        "email_sent": email_sent,
        "internal_email_sent": internal_email_sent,
    }


@app.post("/api/v1/report/client-pdf", tags=["Cliente — Oferta"])
def client_pdf(solution: EPiFullSolution):
    """Descarga directa de la oferta cliente. Publica."""
    path = OUTPUT_DIR / f"Oferta_Cliente_{solution.internal_report.client_id}.pdf"
    generate_client_offer_pdf(solution.client_offer, str(path))
    return FileResponse(path, filename=path.name, media_type="application/pdf")


@app.get("/api/v1/download/{filename}", tags=["Cliente — Oferta"])
def download_generated_file(filename: str):
    """NUEVO — descarga generica de un PDF ya generado en el servidor (p.ej.
    ofertas de repuesto o de equipo de adhesivo, que no se regeneran al
    vuelo como la oferta cliente principal). Solo nombres de archivo sueltos
    (sin rutas) dentro de OUTPUT_DIR, para evitar salir de esa carpeta."""
    safe_name = Path(filename).name  # descarta cualquier componente de ruta
    path = OUTPUT_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Archivo no encontrado (puede haber expirado).")
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
        "download_url": f"/api/v1/download/{client_path.name}",
        "internal_pdf": str(internal_path),
        "lead_id": lead.id,
        "email_sent": email_sent,
    }


# ---------------------------------------------------------------------------
# Repuestos (solo referencia + PVP) — NUEVO, publico, sin login
# ---------------------------------------------------------------------------

@app.get("/api/v1/repuestos/buscar", tags=["Cliente — Repuestos"])
def buscar_repuesto(referencia: str, db: Session = Depends(get_db)):
    """Busca por referencia exacta primero; si no hay resultado exacto,
    busca por coincidencia parcial (hasta 20 resultados)."""
    ref = referencia.strip()
    if not ref:
        raise HTTPException(status_code=400, detail="Indique una referencia.")

    exact = db.query(SparePartModel).filter(SparePartModel.referencia == ref).first()
    if exact:
        rows = [exact]
    else:
        rows = (
            db.query(SparePartModel)
            .filter(SparePartModel.referencia.ilike(f"%{ref}%"))
            .limit(20)
            .all()
        )
    return {
        "query": ref,
        "results": [
            {
                "referencia": r.referencia,
                "descripcion": r.descripcion,
                "fabricante": r.fabricante,
                "precio_eur": r.precio_eur,
            }
            for r in rows
        ],
    }


@app.post("/api/v1/repuestos/oferta", tags=["Cliente — Repuestos"])
def oferta_repuesto(request: SparePartQuoteRequest, db: Session = Depends(get_db)):
    part = db.query(SparePartModel).filter(SparePartModel.referencia == request.referencia.strip()).first()
    if not part:
        raise HTTPException(status_code=404, detail=f"No se encuentra la referencia '{request.referencia}'.")

    final_price = round(part.precio_eur * request.quantity, 2)
    offer = SparePartOffer(
        referencia=part.referencia,
        descripcion=part.descripcion,
        fabricante=part.fabricante,
        quantity=request.quantity,
        unit_price_eur=part.precio_eur,
        final_price_eur=final_price,
        contact=request.contact,
    )

    client_path = OUTPUT_DIR / f"Oferta_Repuesto_{part.referencia}_{uuid.uuid4().hex[:6]}.pdf"
    generate_spare_part_offer_pdf(offer, str(client_path))

    email_sent = False
    if request.contact and request.contact.email:
        email_sent = send_offer_email(
            to_email=request.contact.email,
            contact_name=request.contact.contact_name,
            company_name=request.contact.company_name,
            pdf_path=str(client_path),
            final_price_eur=final_price,
        )

    lead = LeadModel(
        contact_name=request.contact.contact_name if request.contact else None,
        company_name=request.contact.company_name if request.contact else None,
        phone=request.contact.phone if request.contact else None,
        email=request.contact.email if request.contact else None,
        client_id=f"REPUESTO-{part.referencia}",
        final_price_eur=final_price,
        profile_selected="REPUESTO",
        email_sent=email_sent,
        solution_snapshot=offer.model_dump(),
    )
    db.add(lead)
    db.commit()

    return {
        "offer": offer.model_dump(),
        "client_pdf": str(client_path),
        "download_url": f"/api/v1/download/{client_path.name}",
        "email_sent": email_sent,
    }


# ---------------------------------------------------------------------------
# Adhesivo — oferta de equipo (1K, con precio) y seguimiento (2K, sin precio)
# ---------------------------------------------------------------------------

# Referencias reales del catalogo de repuestos de EPi para equipo de adhesivo.
# Bomba de piston por perfil de inversion — mientras no haya tarifa real de
# Graco confirmada, el nivel CALIDAD_PRECIO tambien usa ARO (instruccion de
# Jon: "vete siempre con lo que tengamos"), con un modelo mas economico que
# el de PREMIUM para mantener la diferenciacion de precio entre niveles.
_ADHESIVE_PISTON_PUMP_BY_PROFILE = {
    "BARATA": ("Bomba de pistón para trasiego de adhesivo (Binks)", "02271001",
               "BINKS REINHARDT-TECHNIK GMBH", 1870.50),
    "CALIDAD_PRECIO": ("Bomba de pistón ARO 4-1/4\" 9:1 (2 bolas)", "AF0409C11FF22",
                       "INGERSOLL RAND INDUSTRIAL IRELAND LTD.", 5702.00),
    "PREMIUM": ("Bomba de pistón ARO 4-1/4\" 2:1 (4 bolas, AFX)", "AF0402M11KS48-1",
               "INGERSOLL RAND INDUSTRIAL IRELAND LTD.", 12660.00),
}
# NUEVO — para adhesivos MUY VISCOSOS/PASTOSOS hace falta bomba de clapetas
# (chop-check), no la de bolas normal: tiene un piston "primer" que empuja
# el material y valvulas planas mecanicas en vez de bolas, para materiales
# que no fluyen solos y se pegan a si mismos. Solo tenemos tarifa real ARO
# en el rango de relacion que pidio Jon (23:1 a 46:1) — mismo criterio de
# "vete con lo que tengamos": las tres opciones usan ARO, diferenciadas por
# relacion de compresion en vez de precio (que es igual en ambas).
_ADHESIVE_CHOPCHECK_PUMP_BY_PROFILE = {
    "BARATA": ("Bomba de clapetas (chop-check) ARO 6\" 23:1", "AF0623S11KK47-1",
               "INGERSOLL RAND INDUSTRIAL IRELAND LTD.", 9067.00),
    "CALIDAD_PRECIO": ("Bomba de clapetas (chop-check) ARO 6\" 23:1", "AF0623S11KK47-1",
                       "INGERSOLL RAND INDUSTRIAL IRELAND LTD.", 9067.00),
    "PREMIUM": ("Bomba de clapetas (chop-check) ARO 6\" 46:1", "AF0646S11GF47-1",
               "INGERSOLL RAND INDUSTRIAL IRELAND LTD.", 9067.00),
}
_ADHESIVE_MANUAL_GUN = ("Pistola manual de extrusión Walther Pilot", "V1025000000",
                        "WALTHER SPRITZ-UND LACKIERSYSTEME GMBH", 817.50)
_ADHESIVE_PHOTOCELL = ("Fotocélula", "K96311100", "ZATOR, S.R.L.", 175.00)
_ADHESIVE_SOLENOID = ("Electroválvula", "ELT000321", "ZATOR, S.R.L.", 135.80)
_ADHESIVE_HOSE_PRICE_PER_M = 152.00  # Manguera PTFE alta presion (ref. 00139000, 456€/3m)
_ADHESIVE_HOSE_REF = ("00139000", "BINKS REINHARDT-TECHNIK GMBH")


def _adhesive_elevator_price(drum_liters: float | None) -> float:
    """Precio orientativo del elevador de bidon segun tamaño (dato dado por
    Jon: 9.000-12.000 EUR segun el tamaño). Interpola entre 20 y 200 litros;
    si no se conoce el tamaño, usa un valor intermedio marcado como estimado."""
    if drum_liters is None:
        return 10500.0
    lo, hi = 20.0, 200.0
    price_lo, price_hi = 9000.0, 12000.0
    t = max(0.0, min(1.0, (drum_liters - lo) / (hi - lo)))
    return round(price_lo + t * (price_hi - price_lo), 2)


@app.post("/api/v1/adhesive/oferta", tags=["Cliente — Instalacion de adhesivo"])
def adhesive_oferta(request: AdhesiveOfferRequest, db: Session = Depends(get_db)):
    """SOLO para 1K: genera la oferta de equipo de aplicacion (pistola o
    fotocelula/electrovalvula segun aplicacion, + elevador de bidon) con
    referencia y precio de cada elemento."""
    items = []
    # Orden fisico real del proceso: elevador (baja al bidon) -> bomba de
    # piston (trasiega) -> manguera -> pistola/automatismo.
    elevator_price = _adhesive_elevator_price(request.drum_liters)
    drum_txt = f"{request.drum_liters:g} litros" if request.drum_liters else "a confirmar"
    items.append(AdhesiveEquipmentItem(
        elemento=f"Elevador de bidón ({drum_txt}) — precio orientativo, a confirmar con diámetro exacto",
        referencia="A CONFIRMAR", fabricante="A confirmar según modelo", precio_eur=elevator_price,
    ))

    profile_key = request.profile if request.profile in _ADHESIVE_PISTON_PUMP_BY_PROFILE else "CALIDAD_PRECIO"
    pump_dict = _ADHESIVE_CHOPCHECK_PUMP_BY_PROFILE if request.is_viscous else _ADHESIVE_PISTON_PUMP_BY_PROFILE
    nombre, ref, fab, precio = pump_dict[profile_key]
    items.append(AdhesiveEquipmentItem(elemento=nombre, referencia=ref, fabricante=fab, precio_eur=precio))

    if request.hose_meters:
        hose_ref, hose_fab = _ADHESIVE_HOSE_REF
        hose_price = round(_ADHESIVE_HOSE_PRICE_PER_M * request.hose_meters, 2)
        items.append(AdhesiveEquipmentItem(
            elemento=f"Manguera PTFE alta presión ({request.hose_meters:g} m)",
            referencia=hose_ref, fabricante=hose_fab, precio_eur=hose_price,
        ))

    if request.application_type == "automatica":
        if request.needs_photocell:
            nombre, ref, fab, precio = _ADHESIVE_PHOTOCELL
            items.append(AdhesiveEquipmentItem(elemento=nombre, referencia=ref, fabricante=fab, precio_eur=precio))
        if request.needs_solenoid:
            nombre, ref, fab, precio = _ADHESIVE_SOLENOID
            items.append(AdhesiveEquipmentItem(elemento=nombre, referencia=ref, fabricante=fab, precio_eur=precio))
    else:
        nombre, ref, fab, precio = _ADHESIVE_MANUAL_GUN
        items.append(AdhesiveEquipmentItem(elemento=nombre, referencia=ref, fabricante=fab, precio_eur=precio))

    final_price = round(sum(i.precio_eur for i in items), 2)
    offer = AdhesiveEquipmentOffer(
        application_type=request.application_type,
        profile=profile_key,
        drum_liters=request.drum_liters,
        hose_meters=request.hose_meters,
        items=items,
        final_price_eur=final_price,
        contact=request.contact,
    )

    client_path = OUTPUT_DIR / f"Oferta_Adhesivo_{uuid.uuid4().hex[:6]}.pdf"
    generate_adhesive_equipment_offer_pdf(offer, str(client_path))

    email_sent = False
    if request.contact and request.contact.email:
        email_sent = send_offer_email(
            to_email=request.contact.email,
            contact_name=request.contact.contact_name,
            company_name=request.contact.company_name,
            pdf_path=str(client_path),
            final_price_eur=final_price,
        )

    lead = LeadModel(
        contact_name=request.contact.contact_name if request.contact else None,
        company_name=request.contact.company_name if request.contact else None,
        phone=request.contact.phone if request.contact else None,
        email=request.contact.email if request.contact else None,
        client_id=f"ADHESIVO-1K-{uuid.uuid4().hex[:6]}",
        final_price_eur=final_price,
        profile_selected="ADHESIVO_1K",
        email_sent=email_sent,
        solution_snapshot=offer.model_dump(),
    )
    db.add(lead)
    db.commit()

    return {"offer": offer.model_dump(), "client_pdf": str(client_path), "download_url": f"/api/v1/download/{client_path.name}", "email_sent": email_sent}


@app.post("/api/v1/adhesive/seguimiento", tags=["Cliente — Instalacion de adhesivo"])
def adhesive_seguimiento(request: AdhesiveFollowupRequest, db: Session = Depends(get_db)):
    """SOLO para 2K: no se genera oferta con precio automatica — se guardan
    los datos y se envia un correo al cliente avisando de que un ingeniero
    le contactara."""
    email_sent = False
    if request.contact and request.contact.email:
        email_sent = send_adhesive_followup_email(
            to_email=request.contact.email,
            contact_name=request.contact.contact_name,
            company_name=request.contact.company_name,
            raw_answers=request.raw_answers,
        )

    lead = LeadModel(
        contact_name=request.contact.contact_name if request.contact else None,
        company_name=request.contact.company_name if request.contact else None,
        phone=request.contact.phone if request.contact else None,
        email=request.contact.email if request.contact else None,
        client_id=f"ADHESIVO-2K-{uuid.uuid4().hex[:6]}",
        profile_selected="ADHESIVO_2K",
        email_sent=email_sent,
        solution_snapshot={"raw_answers": request.raw_answers},
    )
    db.add(lead)
    db.commit()

    return {"email_sent": email_sent}
