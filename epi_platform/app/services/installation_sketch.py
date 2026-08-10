"""
installation_sketch — Croquis esquematico de la instalacion (agosto 2026)
============================================================================
Jon pidio que las ofertas incluyan una "foto real y un croquis simulado de
la instalacion". La foto real de producto de fabricantes NO se incluye:
serian imagenes de terceros sacadas de internet, y usarlas en un documento
comercial sin licencia es un riesgo de derechos de autor para la empresa
(ver aviso en la conversacion de origen). Lo que si se genera aqui es un
croquis ESQUEMATICO propio (igual que los que ya tiene la web, estilo plano
tecnico), con cada elemento de la oferta en su caja, en el orden real del
proceso (deposito -> bomba -> conduccion -> válvula/aplicador), usando los
mismos colores de marca que el resto de documentos.

No es un plano de ingenieria a escala — es un esquema de bloques para que
el cliente visualice de un vistazo que elementos incluye la oferta y como
se conectan entre si.
"""
from __future__ import annotations

from typing import List

from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon
from reportlab.lib import colors

_NAVY = colors.HexColor("#0e2b4d")
_BRASS = colors.HexColor("#c69a45")
_INK = colors.HexColor("#1a2433")


def build_installation_sketch(
    labels: List[str],
    width: int = 480,
    height: int = 110,
) -> Drawing:
    """Dibuja `labels` (en orden de proceso) como cajas conectadas por
    flechas, de izquierda a derecha, envolviendo a la siguiente fila si no
    caben todas en una. Cada caja se ajusta al ancho disponible."""
    d = Drawing(width, height)

    n = len(labels)
    if n == 0:
        return d

    margin = 12
    gap = 22  # hueco para la flecha entre cajas
    usable_w = width - 2 * margin
    box_w = (usable_w - gap * (n - 1)) / n if n > 1 else usable_w
    box_w = max(60, min(box_w, 140))
    box_h = 46
    y = height - box_h - 30

    total_w = n * box_w + (n - 1) * gap
    x = (width - total_w) / 2 if total_w < usable_w else margin

    # titulo
    d.add(String(width / 2, height - 16, "Esquema de la instalación (orientativo)",
                  fontSize=8.5, textAnchor="middle", fillColor=_NAVY))

    centers = []
    for i, label in enumerate(labels):
        d.add(Rect(x, y, box_w, box_h, fillColor=colors.HexColor("#f5f2e9"),
                    strokeColor=_NAVY, strokeWidth=1))
        # texto envuelto a mano en hasta 3 lineas cortas
        words = label.split()
        lines, cur = [], ""
        for w_ in words:
            trial = (cur + " " + w_).strip()
            if len(trial) > 16 and cur:
                lines.append(cur)
                cur = w_
            else:
                cur = trial
        if cur:
            lines.append(cur)
        lines = lines[:3]
        line_h = 9
        start_y = y + box_h / 2 + (len(lines) - 1) * line_h / 2
        for j, ln in enumerate(lines):
            d.add(String(x + box_w / 2, start_y - j * line_h, ln,
                          fontSize=6.8, textAnchor="middle", fillColor=_INK))
        centers.append((x, x + box_w, y + box_h / 2))
        x += box_w + gap

    # flechas entre cajas consecutivas
    for i in range(len(centers) - 1):
        x1 = centers[i][1]
        x2 = centers[i + 1][0]
        yc = centers[i][2]
        d.add(Line(x1 + 2, yc, x2 - 6, yc, strokeColor=_BRASS, strokeWidth=1.4))
        d.add(Polygon(
            points=[x2 - 6, yc, x2 - 12, yc + 3.5, x2 - 12, yc - 3.5],
            fillColor=_BRASS, strokeColor=_BRASS,
        ))

    return d
