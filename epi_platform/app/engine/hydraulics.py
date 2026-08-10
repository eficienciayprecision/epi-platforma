"""Motor de calculo hidraulico determinista."""
from __future__ import annotations

import math
from app.schemas.epi_schemas import HydraulicCalculationRequest, HydraulicCalculationResponse


class HydraulicEngine:
    GRAVITY = 9.81

    def __init__(self, req: HydraulicCalculationRequest):
        self.req = req
        self.Q = req.flow_m3h / 3600.0
        self.D = req.diameter_mm / 1000.0
        self.L = req.length_m
        self.roughness = req.roughness_mm / 1000.0
        self.rho = req.density_kg_m3
        self.mu = req.viscosity_cp / 1000.0

    @property
    def area(self) -> float:
        return math.pi * (self.D ** 2) / 4.0

    @property
    def velocity(self) -> float:
        return self.Q / self.area if self.area > 0 else 0.0

    @property
    def reynolds(self) -> float:
        if self.mu <= 0:
            return 0.0
        return (self.rho * self.velocity * self.D) / self.mu

    def friction_factor(self) -> float:
        re = self.reynolds
        if re < 2300:
            return 64.0 / re if re > 0 else 0.03
        rel = self.roughness / self.D
        term = (rel / 3.7) + (5.74 / (re ** 0.9))
        return 0.25 / (math.log10(term) ** 2)

    def compute(self) -> HydraulicCalculationResponse:
        f = self.friction_factor()
        v = self.velocity
        h_f = f * (self.L / self.D) * ((v ** 2) / (2 * self.GRAVITY)) if self.D > 0 else 0.0
        h_m = self.req.k_accessories * ((v ** 2) / (2 * self.GRAVITY))
        h_tot = h_f + h_m
        tdh = self.req.static_head_m + h_tot

        p_hid = (self.rho * self.GRAVITY * self.Q * tdh) / 1000.0
        p_eje = p_hid / 0.65 if 0.65 > 0 else p_hid
        motors = [0.37, 0.55, 0.75, 1.1, 1.5, 2.2, 3.0, 4.0, 5.5, 7.5, 11.0, 15.0]
        motor_kw = next((m for m in motors if m >= p_eje * 1.15), motors[-1])

        warning = None
        if v < 1.0:
            warning = "Velocidad baja (<1.0 m/s): riesgo de sedimentacion."
        elif v > 3.0:
            warning = "Velocidad excesiva (>3.0 m/s): alta perdida de carga y riesgo de golpe de ariete."

        npsha = self.req.npsh_available_m
        return HydraulicCalculationResponse(
            flow_m3h=self.req.flow_m3h,
            fluid_name=self.req.fluid_name,
            diameter_mm=self.req.diameter_mm,
            velocity_ms=round(v, 2),
            reynolds=round(self.reynolds, 0),
            flow_regime="Laminar" if self.reynolds < 2300 else "Turbulento",
            friction_factor=round(f, 4),
            friction_head_loss_m=round(h_f, 2),
            singular_head_loss_m=round(h_m, 2),
            total_head_loss_m=round(h_tot, 2),
            total_dynamic_head_m=round(tdh, 2),
            hydraulic_power_kw=round(p_hid, 2),
            shaft_power_kw=round(p_eje, 2),
            recommended_motor_kw=motor_kw,
            npsh_available_m=npsha,
            npsh_required_max_m=round(npsha * 0.95, 2) if npsha else None,
            velocity_warning=warning,
        )

    # -------------------------------------------------------------------
    # NUEVO — diametro economico optimo (calidad-precio). Un diametro mayor
    # reduce la perdida de carga (menos potencia de bombeo, menos coste
    # energetico) pero cuesta mas de tuberia. Se evaluan los DN estandar y
    # se elige el de menor coste total a lo largo de un periodo de
    # referencia (tuberia + energia), NO simplemente el mas barato de
    # comprar ni el de menor perdida de carga a cualquier precio.
    # -------------------------------------------------------------------

    # DN comercial -> diametro interior aproximado en mm (PVC/acero, uso
    # industrial general). Aproximacion razonable para preseleccionar el
    # tamaño; el precio real de la tuberia en la oferta sigue viniendo del
    # buscador de precios (PriceScraper), esto es solo para decidir el DN.
    STANDARD_DN_MM = {
        15: 16.0, 20: 21.6, 25: 27.4, 32: 36.0, 40: 41.8, 50: 53.0,
        65: 68.8, 80: 80.8, 100: 105.0, 125: 130.0, 150: 155.0, 200: 205.0,
    }
    # Coste aproximado de tuberia instalada, €/metro, por cada DN (PVC/acero
    # industrial, orden de magnitud de mercado — la oferta final usa precios
    # reales via PriceScraper; esto solo sirve para comparar diametros entre si).
    PIPE_COST_EUR_PER_M = {
        15: 4.0, 20: 5.0, 25: 6.5, 32: 8.5, 40: 10.5, 50: 14.0,
        65: 19.0, 80: 24.0, 100: 34.0, 125: 48.0, 150: 65.0, 200: 95.0,
    }
    ENERGY_PRICE_EUR_KWH = 0.15  # aproximacion tarifa industrial
    REFERENCE_YEARS = 3          # periodo de amortizacion tipico para este calculo
    REFERENCE_HOURS_PER_YEAR = 8760  # se asume funcionamiento continuo (caso conservador)

    @classmethod
    def recommend_diameter(
        cls, flow_m3h: float, length_m: float, static_head_m: float,
        k_accessories: float, density_kg_m3: float, viscosity_cp: float,
        roughness_mm: float = 0.03,
    ) -> dict:
        """Evalua los DN estandar y devuelve el de mejor relacion
        calidad-precio (coste de tuberia + coste energetico estimado a
        REFERENCE_YEARS años), junto con el resto de opciones evaluadas
        para que quede claro por que se ha descartado cada una."""
        from app.schemas.epi_schemas import HydraulicCalculationRequest

        options = []
        for dn, id_mm in cls.STANDARD_DN_MM.items():
            req = HydraulicCalculationRequest(
                flow_m3h=flow_m3h, diameter_mm=id_mm, length_m=length_m,
                static_head_m=static_head_m, k_accessories=k_accessories,
                density_kg_m3=density_kg_m3, viscosity_cp=viscosity_cp,
                roughness_mm=roughness_mm, fluid_name="",
            )
            engine = cls(req)
            result = engine.compute()

            pipe_cost = cls.PIPE_COST_EUR_PER_M[dn] * length_m
            energy_cost = (
                result.hydraulic_power_kw / 0.65  # potencia en eje, ~eficiencia media
                * cls.REFERENCE_HOURS_PER_YEAR * cls.REFERENCE_YEARS
                * cls.ENERGY_PRICE_EUR_KWH
            )
            total_cost = pipe_cost + energy_cost

            options.append({
                "dn": dn, "diameter_mm": id_mm, "velocity_ms": result.velocity_ms,
                "total_head_loss_m": result.total_head_loss_m,
                "pipe_cost_eur": round(pipe_cost, 2),
                "energy_cost_eur_3y": round(energy_cost, 2),
                "total_cost_eur_3y": round(total_cost, 2),
                "velocity_ok": 1.0 <= result.velocity_ms <= 3.0,
            })

        # solo se comparan por coste las opciones con velocidad en rango
        # razonable (evita "ganar" con un DN tan pequeño que la velocidad
        # sea absurda, aunque salga barato de tuberia)
        valid = [o for o in options if o["velocity_ok"]] or options
        best = min(valid, key=lambda o: o["total_cost_eur_3y"])

        return {"recommended": best, "all_options": options}
