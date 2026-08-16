"""Aviso interno por email cuando Blas cualifica un lead completo (telefono,
nombre, aplicacion/fluido, y email o preferencia de WhatsApp para la
oferta). Mismo patron de doble transporte que usa el email_service.py de
EPi (Resend API HTTP, o SMTP clasico si se prefiere), pero con variables
BLAS_* propias para poder usar una cuenta/remitente distinto si se quiere."""
from __future__ import annotations

import smtplib
import time
from email.message import EmailMessage

import httpx

from app.blas.config import (
    BLAS_RESEND_API_KEY, BLAS_MAIL_FROM, BLAS_SMTP_HOST, BLAS_SMTP_PORT,
    BLAS_SMTP_USER, BLAS_SMTP_PASSWORD, BLAS_SMTP_USE_TLS,
)

RESEND_API_URL = "https://api.resend.com/emails"


def _send_via_resend(to_email: str, subject: str, body_text: str, timeout: int = 20) -> None:
    resp = httpx.post(
        RESEND_API_URL,
        headers={"Authorization": f"Bearer {BLAS_RESEND_API_KEY}"},
        json={"from": BLAS_MAIL_FROM, "to": [to_email], "subject": subject, "text": body_text},
        timeout=timeout,
    )
    resp.raise_for_status()


def _send_via_smtp(to_email: str, subject: str, body_text: str, timeout: int = 20) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = BLAS_MAIL_FROM
    msg["To"] = to_email
    msg.set_content(body_text)
    with smtplib.SMTP(BLAS_SMTP_HOST, BLAS_SMTP_PORT, timeout=timeout) as server:
        if BLAS_SMTP_USE_TLS:
            server.starttls()
        if BLAS_SMTP_USER and BLAS_SMTP_PASSWORD:
            server.login(BLAS_SMTP_USER, BLAS_SMTP_PASSWORD)
        server.send_message(msg)


def send_internal_lead_notification(to_email: str, subject: str, body_text: str,
                                     attempts: int = 2, retry_wait: int = 3) -> bool:
    if not BLAS_RESEND_API_KEY and not BLAS_SMTP_HOST:
        print("AVISO: no hay BLAS_RESEND_API_KEY ni BLAS_SMTP_HOST configuradas — no se envia el aviso interno.")
        return False
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            if BLAS_RESEND_API_KEY:
                _send_via_resend(to_email, subject, body_text)
            else:
                _send_via_smtp(to_email, subject, body_text)
            print(f"Aviso interno de Blas enviado correctamente a {to_email}")
            return True
        except Exception as e:
            last_error = e
            print(f"  intento {attempt}/{attempts} fallido (aviso interno Blas): {type(e).__name__}: {e}")
            if attempt < attempts:
                time.sleep(retry_wait)
    print(f"ERROR enviando aviso interno de Blas a {to_email}: {type(last_error).__name__}: {last_error}")
    return False
