"""
Configuracion de Blas — variables de entorno.

Blas vive ahora DENTRO del mismo servicio y base de datos que EPi (ver
app/main.py: se monta como sub-router bajo /blas). Comparte DATABASE_URL
con EPi a proposito — mismo Postgres, tablas propias (`conversations`,
`messages`) sin colision con las de EPi. El resto de variables son propias
de Blas (prefijo WHATSAPP_ / BLAS_) para no chocar con las de EPi.
"""
from __future__ import annotations

import os


def _get(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


# --- WhatsApp Cloud API (Meta) ------------------------------------------
# Panel: business.facebook.com -> WhatsApp -> Configuracion de la API
WHATSAPP_TOKEN = _get("WHATSAPP_TOKEN")  # token permanente del System User
WHATSAPP_PHONE_NUMBER_ID = _get("WHATSAPP_PHONE_NUMBER_ID")  # ID numerico del numero emisor (NO el telefono en si)
WHATSAPP_VERIFY_TOKEN = _get("WHATSAPP_VERIFY_TOKEN", "blas-verify-token")  # lo inventas tu, se usa al configurar el webhook en Meta
WHATSAPP_API_VERSION = _get("WHATSAPP_API_VERSION", "v20.0")
WHATSAPP_GRAPH_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}"

# Nombre EXACTO de la plantilla aprobada en Meta para el primer mensaje
# (obligatorio: a un numero que no nos ha escrito antes solo se le puede
# contactar con una plantilla pre-aprobada, no con texto libre). Ver README.
WHATSAPP_OPENING_TEMPLATE_NAME = _get("WHATSAPP_OPENING_TEMPLATE_NAME", "blas_apertura")
WHATSAPP_OPENING_TEMPLATE_LANG = _get("WHATSAPP_OPENING_TEMPLATE_LANG", "es")

# --- Notificacion interna por email cuando un lead queda cualificado ----
# Mismo mecanismo que EPi (Resend o SMTP), pero variables propias de Blas
# para poder usar una cuenta/API key distinta si se prefiere.
BLAS_RESEND_API_KEY = _get("BLAS_RESEND_API_KEY")
BLAS_MAIL_FROM = _get("BLAS_MAIL_FROM", "blas@eficienciayprecisionindustrial.com")
BLAS_SMTP_HOST = _get("BLAS_SMTP_HOST")
BLAS_SMTP_PORT = int(_get("BLAS_SMTP_PORT", "587"))
BLAS_SMTP_USER = _get("BLAS_SMTP_USER")
BLAS_SMTP_PASSWORD = _get("BLAS_SMTP_PASSWORD")
BLAS_SMTP_USE_TLS = _get("BLAS_SMTP_USE_TLS", "true").lower() == "true"
BLAS_INTERNAL_NOTIFY_EMAIL = _get("BLAS_INTERNAL_NOTIFY_EMAIL", "ingenieria@eficienciayprecisionindustrial.com")

# --- Bandeja interna (para ver/responder conversaciones) ----------------
# Token compartido simple para proteger /blas/api/internal/*. Cambialo en Render.
BLAS_INTERNAL_TOKEN = _get("BLAS_INTERNAL_TOKEN", "cambia-este-token")
