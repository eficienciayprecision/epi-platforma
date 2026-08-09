"""
pump_curve — Curva caudal/altura de la bomba, con el punto de trabajo (V9)
============================================================================
EPi no tiene todavia la curva REAL de fabricante para la inmensa mayoria de
su catalogo (eso es un trabajo de busqueda referencia a referencia, como el
que se hizo para caudal/potencia/presion — ver conversacion de origen).
Mientras tanto, esta funcion genera una curva ORIENTATIVA a partir de los
dos datos que si tenemos siempre (caudal maximo y altura/presion maxima),
con la forma tipica que le corresponde a cada tecnologia:

- Bombas volumetricas (neumatica, peristaltica, tornillo helicoidal,
  engranajes): el caudal es casi constante frente a la presion, con una
  ligera caida por deslizamiento interno al acercarse a la presion maxima.
  La curva es casi vertical.
- Bombas centrifugas: curva descendente clasica, con altura maxima a
  caudal cero (cierre) y caudal maximo a altura reducida (embalamiento).

Cuando `pump.curve_reference_url` esta informado (curva real localizada),
el PDF debe mostrar el enlace a la ficha oficial ademas de (o en vez de)
esta curva aproximada — eso se gestiona en pdf_generator.py, no aqui.
"""
from __future__ import annotations

from typing import List, Tuple

from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors

from app.schemas.epi_schemas import PumpTechnology, SelectedPump

_VOLUMETRIC = {
    PumpTechnology.NEUMATICA_DOBLE_MEMBRANA,
    PumpTechnology.PERISTALTICA,
    PumpTechnology.TORNILLO_HELICOIDAL,
    PumpTechnology.ENGRANAJES,
}


def approximate_curve_points(pump: SelectedPump) -> List[Tuple[float, float]]:
    """(caudal m3/h, altura m.c.f.) a lo largo de la curva orientativa,
    de menor a mayor altura. NO es la curva real del fabricante."""
    q_max = pump.max_flow_m3h
    h_max = pump.max_head_m

    if pump.technology in _VOLUMETRIC:
        # Caudal casi constante con la presion, con ligera caida (deslizamiento).
        return [
            (round(q_max * 0.98, 2), 0.0),
            (round(q_max * 0.94, 2), round(h_max * 0.5, 1)),
            (round(q_max * 0.88, 2), round(h_max, 1)),
        ]

    # Centrifuga: cierre (Q=0) a ~1.25x la altura de catalogo, pasando por el
    # punto de catalogo hacia caudal medio, y embalamiento a caudal ~1.3x con
    # altura muy reducida.
    h0 = round(h_max * 1.25, 1)
    q_rated = q_max * 0.75
    return [
        (0.0, h0),
        (round(q_rated * 0.5, 2), round(h0 * 0.93, 1)),
        (round(q_rated, 2), round(h_max, 1)),
        (round(q_max, 2), round(h_max * 0.65, 1)),
        (round(q_max * 1.25, 2), round(h_max * 0.25, 1)),
    ]


def build_curve_drawing(
    pump: SelectedPump,
    operating_flow_m3h: float,
    operating_head_m: float,
    width: int = 260,
    height: int = 160,
) -> Drawing:
    """Devuelve un reportlab Drawing con la curva orientativa de la bomba y
    el punto de trabajo solicitado marcado encima, listo para insertar en
    el PDF con `elements.append(drawing)`."""
    curve = approximate_curve_points(pump)

    d = Drawing(width, height)
    lp = LinePlot()
    lp.x = 35
    lp.y = 25
    lp.width = width - 55
    lp.height = height - 45

    lp.data = [curve, [(operating_flow_m3h, operating_head_m)]]

    lp.lines[0].strokeColor = colors.HexColor("#1F3864")
    lp.lines[0].strokeWidth = 1.6
    lp.lines[0].symbol = None

    lp.lines[1].symbol = makeMarker("Circle")
    lp.lines[1].symbol.fillColor = colors.HexColor("#C0392B")
    lp.lines[1].symbol.strokeColor = colors.HexColor("#C0392B")
    lp.lines[1].symbol.size = 5
    lp.lines[1].strokeColor = colors.transparent

    all_q = [p[0] for p in curve] + [operating_flow_m3h]
    all_h = [p[1] for p in curve] + [operating_head_m]
    q_axis_max = max(all_q) * 1.1 or 1.0
    h_axis_max = max(all_h) * 1.15 or 1.0

    lp.xValueAxis.valueMin = 0
    lp.xValueAxis.valueMax = round(q_axis_max, 1)
    lp.xValueAxis.labels.fontSize = 7
    lp.yValueAxis.valueMin = 0
    lp.yValueAxis.valueMax = round(h_axis_max, 1)
    lp.yValueAxis.labels.fontSize = 7

    d.add(lp)
    d.add(String(width / 2, height - 10, "Caudal (m3/h) vs Altura (m.c.f.)",
                  fontSize=8, textAnchor="middle", fillColor=colors.HexColor("#1F3864")))
    d.add(String(10, 5, "— Curva orientativa   •  Punto de trabajo solicitado",
                 fontSize=6.5, fillColor=colors.grey))
    return d
