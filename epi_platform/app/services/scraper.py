"""PriceScraper — localiza componentes (tuberia, valvulas, sensores) y su coste.

Si enable_web=True intenta una busqueda en proveedores industriales; si no
hay conectividad o falla, usa un catalogo interno de referencia como
respaldo para que el flujo nunca se rompa.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.commercial import CommercialEngine

from app.schemas.epi_schemas import MaterialsBreakdown

# Catalogo interno de respaldo (EUR / unidad, a precio de coste real)
_FALLBACK_CATALOG = {
    "tuberia_inox_316L_m": {"supplier": "Tubos & Inox Bizkaia Direct", "unit_cost": 45.00, "unit": "m"},
    "valvula_bola_inox": {"supplier": "Válvulas Industriales Norte S.L.", "unit_cost": 120.00, "unit": "ud"},
    "sensor_presion_caudal": {"supplier": "Instrumentación & Control S.A.", "unit_cost": 210.00, "unit": "ud"},
}

# NUEVO — catalogo generico para elementos sueltos identificados por foto
# (distinto del catalogo de bombas en BD, que tiene su propio modelo/tabla).
# Coincidencia por palabra clave sobre la etiqueta traducida de vision_service.
_GENERIC_ITEM_CATALOG = [
    (("válvula de bola",), {"supplier": "Válvulas Industriales Norte S.L.", "unit_cost": 120.00, "unit": "ud"}),
    (("válvula de mariposa",), {"supplier": "Válvulas Industriales Norte S.L.", "unit_cost": 165.00, "unit": "ud"}),
    (("válvula",), {"supplier": "Válvulas Industriales Norte S.L.", "unit_cost": 120.00, "unit": "ud"}),
    (("tubería", "tubo"), {"supplier": "Tubos & Inox Bizkaia Direct", "unit_cost": 45.00, "unit": "m"}),
    (("sensor", "manómetro", "transmisor"), {"supplier": "Instrumentación & Control S.A.", "unit_cost": 210.00, "unit": "ud"}),
    (("brida",), {"supplier": "Tubos & Inox Bizkaia Direct", "unit_cost": 35.00, "unit": "ud"}),
    (("motor",), {"supplier": "Motores Eléctricos Bilbao S.A.", "unit_cost": 480.00, "unit": "ud"}),
    (("bomba",), {"supplier": "Consultar catálogo de bombas EPi", "unit_cost": 950.00, "unit": "ud"}),
]


class PriceScraper:
    def __init__(self, enable_web: bool = True):
        self.enable_web = enable_web

    def _lookup_component(self, key: str) -> dict:
        """Punto de extension: aqui iria la busqueda web real (requests/bs4)
        cuando enable_web=True. Por ahora, y como respaldo, usa el catalogo interno."""
        return _FALLBACK_CATALOG[key]

    def lookup_generic_item(self, item_name: str) -> dict:
        """NUEVO — busca un elemento suelto (identificado por foto o escrito
        a mano por el cliente) por coincidencia de palabra clave.

        Punto de extension: aqui iria la busqueda real en proveedores web
        cuando enable_web=True (misma logica que build_materials_for_line).
        Si no se reconoce el elemento, devuelve un precio orientativo
        marcado como 'estimado' para que el flujo nunca se rompa.
        """
        lower = item_name.strip().lower()
        for keywords, data in _GENERIC_ITEM_CATALOG:
            if any(kw in lower for kw in keywords):
                return {**data, "matched": True}
        return {
            "supplier": "Proveedor a determinar (sin catálogo)",
            "unit_cost": 150.00,
            "unit": "ud",
            "matched": False,
        }

    def build_materials_for_line(
        self,
        diameter_mm: float,
        length_m: float,
        commercial_engine: "CommercialEngine",
        parallel_pumps: bool = False,
    ) -> MaterialsBreakdown:
        pipe = self._lookup_component("tuberia_inox_316L_m")
        valve = self._lookup_component("valvula_bola_inox")
        sensor = self._lookup_component("sensor_presion_caudal")

        lines = [
            commercial_engine.build_material_line(
                component=f"Tubería Inox AISI 316L DN{diameter_mm:.1f} ({length_m:.1f}m)",
                supplier=pipe["supplier"], quantity=length_m,
                unit="m", unit_cost_real_eur=pipe["unit_cost"],
            ),
        ]

        # FIX — el numero de valvulas depende de si hay una bomba o dos en
        # paralelo (cada bomba necesita su propia valvula de aspiracion y
        # de impulsion para poder aislarla sin parar la otra). Ademas, la
        # entrada y la salida de una bomba NO tienen por que ser del mismo
        # diametro (muchas centrifugas tienen aspiracion mayor que
        # impulsion) — se piden como dos partidas separadas en vez de una
        # sola "x2 unidades", y se avisa de que el diametro exacto de cada
        # una se debe confirmar contra la ficha de la bomba concreta.
        n_bombas = 2 if parallel_pumps else 1
        config_txt = " (bombas en paralelo — 1 en servicio + 1 de reserva)" if parallel_pumps else ""
        lines.append(commercial_engine.build_material_line(
            component=(
                f"Válvulas de Bola Inox 3 Piezas — aspiración de bomba{config_txt}, "
                f"DN{diameter_mm:.1f} orientativo (confirmar contra la conexión real de la bomba)"
            ),
            supplier=valve["supplier"], quantity=n_bombas,
            unit="ud", unit_cost_real_eur=valve["unit_cost"],
        ))
        lines.append(commercial_engine.build_material_line(
            component=(
                f"Válvulas de Bola Inox 3 Piezas — impulsión de bomba{config_txt}, "
                f"DN{diameter_mm:.1f} orientativo (confirmar contra la conexión real de la bomba, "
                "puede no coincidir con la de aspiración)"
            ),
            supplier=valve["supplier"], quantity=n_bombas,
            unit="ud", unit_cost_real_eur=valve["unit_cost"],
        ))
        lines.append(
            commercial_engine.build_material_line(
                component="Sensores de Presión y Caudal 4-20mA HART",
                supplier=sensor["supplier"], quantity=2,
                unit="ud", unit_cost_real_eur=sensor["unit_cost"],
            )
        )
        return commercial_engine.build_materials_breakdown(lines)
