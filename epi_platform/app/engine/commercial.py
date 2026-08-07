"""
CommercialEngine — Motor de cálculo comercial de EPI
====================================================
Aplica de forma estricta:
  - +40 % de margen comercial sobre componentes web
  - +38 % de contingencia sobre el subtotal comercial

El documento cliente no desglosa costes reales de compra ni el 38 %; el
cliente ve un precio final único ("llave en mano"), como cualquier
presupuesto cerrado de ingeniería.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from app.schemas.epi_schemas import (
    InvestmentProfile,
    PumpTechnology,
    HydraulicCalculationResponse,
    MaterialLine,
    MaterialsBreakdown,
    SelectedPump,
    CommercialBreakdown,
    ClientOfferMaterial,
    ClientOffer,
    InternalReport,
    EPiFullSolution,
    ContactInfo,
    ItemQuoteRequest,
    SingleItemOffer,
    SingleItemInternalReport,
    SingleItemSolution,
)


class CommercialEngine:
    """Motor comercial determinista. No depende de IA. Solo de reglas de negocio."""

    WEB_MARGIN_PCT: float = 40.0
    CONTINGENCY_PCT: float = 38.0

    def __init__(
        self,
        labor_engineering_eur: float = 1800.0,
        default_client_id_prefix: str = "REF-IND",
    ):
        self.labor_engineering_eur = labor_engineering_eur
        self.default_client_id_prefix = default_client_id_prefix

    # -------------------------------------------------------------------------
    def build_material_line(
        self,
        component: str,
        supplier: str,
        quantity: float,
        unit: str,
        unit_cost_real_eur: float,
    ) -> MaterialLine:
        total_real = round(quantity * unit_cost_real_eur, 2)
        pvp = round(total_real * (1 + self.WEB_MARGIN_PCT / 100), 2)

        return MaterialLine(
            component=component,
            supplier=supplier,
            quantity=quantity,
            unit=unit,
            unit_cost_real_eur=unit_cost_real_eur,
            total_cost_real_eur=total_real,
            margin_pct=self.WEB_MARGIN_PCT,
            pvp_with_margin_eur=pvp,
        )

    def build_materials_breakdown(self, lines: List[MaterialLine]) -> MaterialsBreakdown:
        total_real = round(sum(l.total_cost_real_eur for l in lines), 2)
        total_pvp = round(sum(l.pvp_with_margin_eur for l in lines), 2)

        return MaterialsBreakdown(
            lines=lines,
            total_cost_real_eur=total_real,
            total_pvp_with_40_eur=total_pvp,
        )

    # -------------------------------------------------------------------------
    def calculate_commercial(
        self,
        pump_base_cost_eur: float,
        materials: MaterialsBreakdown,
        labor_engineering_eur: Optional[float] = None,
    ) -> CommercialBreakdown:
        labor = labor_engineering_eur if labor_engineering_eur is not None else self.labor_engineering_eur

        subtotal = round(
            pump_base_cost_eur + materials.total_pvp_with_40_eur + labor, 2,
        )

        contingency_amount = round(subtotal * (self.CONTINGENCY_PCT / 100), 2)
        final_price = round(subtotal * (1 + self.CONTINGENCY_PCT / 100), 2)

        cost_real_total = pump_base_cost_eur + materials.total_cost_real_eur + labor
        gross_profit = round(final_price - cost_real_total, 2)

        return CommercialBreakdown(
            pump_base_cost_eur=pump_base_cost_eur,
            materials_pvp_40_eur=materials.total_pvp_with_40_eur,
            labor_engineering_eur=labor,
            subtotal_commercial_eur=subtotal,
            contingency_pct=self.CONTINGENCY_PCT,
            contingency_amount_eur=contingency_amount,
            final_client_price_eur=final_price,
            estimated_gross_profit_eur=gross_profit,
        )

    # -------------------------------------------------------------------------
    def build_client_offer(
        self,
        commercial: CommercialBreakdown,
        pump: SelectedPump,
        materials: MaterialsBreakdown,
        hydraulics: HydraulicCalculationResponse,
        contact: Optional[ContactInfo] = None,
    ) -> ClientOffer:
        client_materials: List[ClientOfferMaterial] = []

        for line in materials.lines:
            if line.unit in ("m", "metros"):
                qty_display = f"{line.quantity:.1f} metros"
            else:
                qty_display = f"{int(line.quantity)} unidades"

            element_name = self._friendly_element_name(line.component)

            client_materials.append(
                ClientOfferMaterial(
                    element=element_name,
                    specification=line.component.split("(")[0].strip()
                    if "(" in line.component
                    else line.component,
                    quantity_display=qty_display,
                )
            )

        return ClientOffer(
            final_price_eur=commercial.final_client_price_eur,
            pump=pump,
            materials=client_materials,
            fluid_name=hydraulics.fluid_name,
            flow_m3h=hydraulics.flow_m3h,
            total_head_loss_m=hydraulics.total_head_loss_m,
            tdh_m=hydraulics.total_dynamic_head_m,
            velocity_ms=hydraulics.velocity_ms,
            npsh_available_m=hydraulics.npsh_available_m,
            contact=contact,
        )

    # -------------------------------------------------------------------------
    def build_internal_report(
        self,
        commercial: CommercialBreakdown,
        pump: SelectedPump,
        materials: MaterialsBreakdown,
        hydraulics: HydraulicCalculationResponse,
        client_id: Optional[str] = None,
        network_status: str = "Tuberías Soldadas (Sin Parada)",
        consultation_date: Optional[date] = None,
        contact: Optional[ContactInfo] = None,
    ) -> InternalReport:
        if client_id is None:
            client_id = f"{self.default_client_id_prefix}-BILBAO-0000"

        if consultation_date is None:
            consultation_date = date.today()

        instructions = (
            f"Comprar componentes en los distribuidores indicados utilizando la cuenta "
            f"corporativa de Eficiencia y Precisión Industrial S.L. "
            f"La bomba debe solicitarse a la marca {pump.brand}."
        )

        return InternalReport(
            consultation_date=consultation_date,
            client_id=client_id,
            network_status=network_status,
            hydraulics=hydraulics,
            materials_breakdown=materials,
            commercial=commercial,
            selected_pump=pump,
            engineer_instructions=instructions,
            contact=contact,
        )

    # -------------------------------------------------------------------------
    def build_full_solution(
        self,
        profile: InvestmentProfile,
        pump: SelectedPump,
        materials: MaterialsBreakdown,
        hydraulics: HydraulicCalculationResponse,
        client_id: Optional[str] = None,
        labor_engineering_eur: Optional[float] = None,
        network_status: str = "Tuberías Soldadas (Sin Parada)",
        contact: Optional[ContactInfo] = None,
    ) -> EPiFullSolution:
        """Punto de entrada principal tras el botón "Nosotros nos encargamos"."""
        commercial = self.calculate_commercial(
            pump_base_cost_eur=pump.base_cost_eur,
            materials=materials,
            labor_engineering_eur=labor_engineering_eur,
        )

        client_offer = self.build_client_offer(
            commercial=commercial, pump=pump, materials=materials,
            hydraulics=hydraulics, contact=contact,
        )

        internal_report = self.build_internal_report(
            commercial=commercial, pump=pump, materials=materials,
            hydraulics=hydraulics, client_id=client_id,
            network_status=network_status, contact=contact,
        )

        return EPiFullSolution(
            profile_selected=profile,
            hydraulics=hydraulics,
            selected_pump=pump,
            materials_breakdown=materials,
            commercial=commercial,
            client_offer=client_offer,
            internal_report=internal_report,
        )

    # -------------------------------------------------------------------------
    # NUEVO — Oferta de un unico elemento identificado por foto
    # -------------------------------------------------------------------------
    def build_single_item_solution(
        self,
        request: ItemQuoteRequest,
        supplier: str,
        unit_cost_real_eur: float,
        unit: str,
        client_id: Optional[str] = None,
        labor_engineering_eur: float = 0.0,
    ) -> SingleItemSolution:
        """Aplica las mismas reglas comerciales (+40% / +38%) que el resto
        de EPi, pero a un solo elemento en vez de a una instalacion completa."""

        line = self.build_material_line(
            component=request.item_name,
            supplier=supplier,
            quantity=request.quantity,
            unit=unit,
            unit_cost_real_eur=unit_cost_real_eur,
        )
        materials = self.build_materials_breakdown([line])
        commercial = self.calculate_commercial(
            pump_base_cost_eur=0.0,
            materials=materials,
            labor_engineering_eur=labor_engineering_eur,
        )

        if client_id is None:
            client_id = f"{self.default_client_id_prefix}-ITEM-0000"

        client_offer = SingleItemOffer(
            item_name=request.item_name,
            supplier=supplier,
            quantity=request.quantity,
            unit=unit,
            final_price_eur=commercial.final_client_price_eur,
            contact=request.contact,
        )
        internal_report = SingleItemInternalReport(
            consultation_date=date.today(),
            client_id=client_id,
            item_line=line,
            commercial=commercial,
            contact=request.contact,
        )
        return SingleItemSolution(client_offer=client_offer, internal_report=internal_report)

    @staticmethod
    def _friendly_element_name(component: str) -> str:
        lower = component.lower()
        if "tubería" in lower or "tubo" in lower:
            return "Tubería de Impulsión/Aspiración"
        if "válvula" in lower:
            return "Válvulas de Regulación y Retención"
        if "sensor" in lower or "transmisor" in lower or "caudal" in lower:
            return "Sensorización e Instrumentación"
        return component.split("(")[0].strip()
