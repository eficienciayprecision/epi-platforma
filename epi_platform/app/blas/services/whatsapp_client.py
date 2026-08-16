"""
Cliente minimo de la API de WhatsApp Cloud (Meta).

CONCEPTO CLAVE — ventana de 24h y plantillas:
Meta solo deja mandar texto libre a un numero si ese numero nos ha escrito
en las ultimas 24h ("customer service window"). Para el PRIMER mensaje a un
cliente que aun no nos ha escrito (justo el caso de Blas: el cliente da su
telefono en la web, todavia no nos ha escrito por WhatsApp) es OBLIGATORIO
usar una "plantilla" (template) previamente creada y aprobada en Meta
Business Manager. Una vez el cliente responde, se abre la ventana de 24h y
ya se puede usar texto libre con normalidad — por eso el resto de la
conversacion (nombre, aplicacion, email...) se manda con send_text().

Ver README (seccion Blas) para como crear y aprobar la plantilla de apertura.
"""
from __future__ import annotations

from typing import Optional

import httpx

from app.blas.config import (
    WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_GRAPH_URL,
    WHATSAPP_OPENING_TEMPLATE_NAME, WHATSAPP_OPENING_TEMPLATE_LANG,
)


class WhatsAppNotConfigured(Exception):
    """WHATSAPP_TOKEN o WHATSAPP_PHONE_NUMBER_ID no estan configuradas todavia."""


def _messages_url() -> str:
    if not WHATSAPP_PHONE_NUMBER_ID:
        raise WhatsAppNotConfigured("Falta WHATSAPP_PHONE_NUMBER_ID")
    return f"{WHATSAPP_GRAPH_URL}/{WHATSAPP_PHONE_NUMBER_ID}/messages"


def _headers() -> dict:
    if not WHATSAPP_TOKEN:
        raise WhatsAppNotConfigured("Falta WHATSAPP_TOKEN")
    return {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}


def _normalize_phone(phone: str) -> str:
    """Deja solo digitos (la API de WhatsApp quiere el numero en formato
    internacional sin '+', ej. 34600111222)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits


def send_opening_template(to_phone: str, timeout: int = 20) -> dict:
    """Primer contacto — plantilla aprobada, sin ventana de 24h abierta
    todavia. Devuelve la respuesta JSON de Meta (incluye el message id)."""
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(to_phone),
        "type": "template",
        "template": {
            "name": WHATSAPP_OPENING_TEMPLATE_NAME,
            "language": {"code": WHATSAPP_OPENING_TEMPLATE_LANG},
        },
    }
    resp = httpx.post(_messages_url(), headers=_headers(), json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def send_text(to_phone: str, body: str, timeout: int = 20) -> dict:
    """Texto libre — solo funciona dentro de la ventana de 24h (el cliente
    ya nos ha escrito). Se usa para todo el resto de la conversacion."""
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(to_phone),
        "type": "text",
        "text": {"body": body, "preview_url": False},
    }
    resp = httpx.post(_messages_url(), headers=_headers(), json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def parse_inbound_webhook(payload: dict) -> Optional[dict]:
    """Extrae {phone, text, wa_message_id} del JSON crudo que manda Meta al
    webhook. Devuelve None si el evento no es un mensaje de texto entrante
    (p.ej. es un "status" de entrega/lectura, que Meta tambien manda al
    mismo webhook y hay que ignorar)."""
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages")
        if not messages:
            return None  # es un evento de "status", no un mensaje nuevo
        msg = messages[0]
        phone = msg.get("from")
        text = None
        if msg.get("type") == "text":
            text = msg["text"]["body"]
        else:
            # imagenes, audios, etc. — de momento Blas solo entiende texto
            # en esta primera version del flujo comercial inicial.
            text = None
        return {"phone": phone, "text": text, "wa_message_id": msg.get("id"), "type": msg.get("type")}
    except (KeyError, IndexError, TypeError):
        return None
