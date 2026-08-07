"""Optimizador energetico (VFD vs estrangulamiento)."""
from __future__ import annotations


class EnergyOptimizer:
    def __init__(
        self,
        flow_m3h: float,
        head_m: float,
        hours_per_year: int = 8000,
        energy_cost_kwh: float = 0.15,
        rho: float = 1000.0,
    ):
        self.Q = flow_m3h
        self.H = head_m
        self.hours = hours_per_year
        self.kwh_cost = energy_cost_kwh
        self.rho = rho

    def calculate_power_kw(self, pump_efficiency: float, motor_efficiency: float) -> float:
        return (self.Q * self.H * self.rho * 9.81) / (3600 * pump_efficiency * motor_efficiency)

    def compare_vfd_savings(
        self,
        current_eff: float = 0.60,
        new_eff_with_vfd: float = 0.78,
        vfd_cost_eur: float = 2500.0,
    ) -> dict:
        kw_old = self.calculate_power_kw(current_eff, 0.90)
        cost_old = kw_old * self.hours * self.kwh_cost
        kw_new = self.calculate_power_kw(new_eff_with_vfd, 0.95)
        cost_new = kw_new * self.hours * self.kwh_cost
        savings = cost_old - cost_new
        roi = (vfd_cost_eur / savings) * 12 if savings > 0 else 0
        return {
            "current_annual_cost_eur": round(cost_old, 2),
            "optimized_annual_cost_eur": round(cost_new, 2),
            "annual_savings_eur": round(savings, 2),
            "roi_months": round(roi, 1),
        }
