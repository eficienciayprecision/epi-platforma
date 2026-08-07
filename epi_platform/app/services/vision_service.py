"""NUEVO — Identificacion de un elemento industrial suelto a partir de una foto.

Usa Google Cloud Vision API por debajo (deteccion/etiquetado de objetos),
pero el cliente nunca ve el nombre del proveedor: solo ve "EPi ha
analizado la foto". Es un modulo DISTINTO del stub /api/v1/photo/redesign
(que rediseña una instalacion completa calibrando escala); este solo
identifica UN elemento suelto para poder ofertarlo individualmente.

Configuracion por variable de entorno:
  EPI_VISION_API_KEY

Si no esta configurada, se usa una respuesta de respaldo (source =
"fallback_sin_configurar") que no rompe el flujo, pero pide siempre
confirmacion manual al cliente -- igual que si la API hubiese respondido
con baja confianza.
"""
from __future__ import annotations

import base64
import os
from typing import Optional

import httpx

from app.schemas.epi_schemas import ObjectIdentificationResult

# Vocabulario de referencia: cuando la API de vision devuelve una etiqueta
# generica en ingles, la traducimos a los terminos que ya usa EPi en el
# resto del sistema (catalogo, PDFs, motor comercial).
_LABEL_TRANSLATION = {
    "valve": "Válvula",
    "ball valve": "Válvula de Bola Inox",
    "butterfly valve": "Válvula de Mariposa",
    "pump": "Bomba",
    "centrifugal pump": "Bomba Centrífuga",
    "pipe": "Tramo de Tubería",
    "pipe fitting": "Accesorio de Tubería",
    "sensor": "Sensor de Presión/Caudal",
    "pressure gauge": "Manómetro",
    "electric motor": "Motor Eléctrico",
    "flange": "Brida",
}


def _translate_label(raw_label: str) -> str:
    key = raw_label.strip().lower()
    return _LABEL_TRANSLATION.get(key, raw_label.strip().title())


def _fallback_result() -> ObjectIdentificationResult:
    return ObjectIdentificationResult(
        detected_label="Elemento no identificado automáticamente",
        confidence=0.0,
        suggestion_text=(
            "No hemos podido analizar la foto automáticamente. "
            "¿Puedes indicarnos tú qué elemento es (p. ej. 'válvula de bola "
            "DN50', 'bomba centrífuga', 'sensor de presión')?"
        ),
        source="fallback_sin_configurar",
    )


def identify_object_from_image(image_bytes: bytes) -> ObjectIdentificationResult:
    """Identifica el elemento principal de una foto. Nunca lanza excepcion:
    si la API no esta configurada o falla, degrada a una respuesta de
    respaldo que sigue permitiendo continuar el flujo (con confirmacion
    manual del cliente)."""

    api_key = os.getenv("EPI_VISION_API_KEY")
    if not api_key:
        return _fallback_result()

    try:
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "requests": [
                {
                    "image": {"content": encoded},
                    "features": [{"type": "OBJECT_LOCALIZATION", "maxResults": 5}],
                }
            ]
        }
        url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        annotations = data.get("responses", [{}])[0].get(
            "localizedObjectAnnotations", []
        )
        if not annotations:
            return _fallback_result()

        best = max(annotations, key=lambda a: a.get("score", 0.0))
        raw_label = best.get("name", "")
        confidence = float(best.get("score", 0.0))
        friendly = _translate_label(raw_label)

        return ObjectIdentificationResult(
            detected_label=friendly,
            confidence=round(confidence, 2),
            suggestion_text=(
                f"Esto parece ser: {friendly} "
                f"(confianza {confidence * 100:.0f}%). "
                "¿Es correcto, o quieres corregirlo?"
            ),
            source="vision_api",
        )
    except Exception:
        # No tumbar el flujo si la API falla; se pide confirmacion manual.
        return _fallback_result()
