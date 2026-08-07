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
