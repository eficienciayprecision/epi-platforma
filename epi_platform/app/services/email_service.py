"""NUEVO — Envio automatico de la oferta (PDF) al email del contacto.

Configuracion por variables de entorno:
  EPI_SMTP_HOST, EPI_SMTP_PORT, EPI_SMTP_USER, EPI_SMTP_PASSWORD,
  EPI_SMTP_USE_TLS (true/false), EPI_MAIL_FROM
Si EPI_SMTP_HOST no esta definido, el envio se omite silenciosamente
(util en desarrollo/local) y se devuelve sent=False.

IMPORTANTE sobre EPI_MAIL_FROM=epi@eficienciayprecisionindustrial.com:
la mayoria de servidores SMTP exigen que el usuario autenticado (EPI_SMTP_USER)
coincida con el remitente del "From", o que este autorizado explicitamente a
enviar en su nombre (alias/"Send As"). Esto NO requiere dar a EPi acceso a
leer el correo de esa cuenta (bandeja de entrada, contactos, etc.) — solo una
credencial de ENVIO (SMTP) para esa direccion. Segun el proveedor de correo:
  - Google Workspace / Gmail: crear la cuenta epi@... y generar una
    "contraseña de aplicación" (no la contraseña normal) para SMTP, o
    autorizarla como alias "Enviar correo como" desde otra cuenta.
  - Microsoft 365 / Outlook: crear un buzon compartido o cuenta epi@... y
    usar SMTP AUTH o una App Password; alternativamente enviar via Microsoft
    Graph API con permisos de solo-envio.
  - Proveedores tipo SendGrid/Mailgun/Amazon SES: mas recomendable a medio
    plazo — se verifica el dominio una vez (registros SPF/DKIM) y se envia
    "como" epi@eficienciayprecisionindustrial.com sin exponer ninguna
    contraseña de un buzon real, con mejor entregabilidad.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional


def send_offer_email(
    to_email: str,
    contact_name: Optional[str],
    company_name: Optional[str],
    pdf_path: str,
    final_price_eur: Optional[float] = None,
) -> bool:
    host = os.getenv("EPI_SMTP_HOST")
    if not host:
        # Sin configuracion SMTP: no se envia, pero no se rompe el flujo.
        return False

    port = int(os.getenv("EPI_SMTP_PORT", "587"))
    user = os.getenv("EPI_SMTP_USER")
    password = os.getenv("EPI_SMTP_PASSWORD")
    use_tls = os.getenv("EPI_SMTP_USE_TLS", "true").lower() == "true"
    mail_from = os.getenv("EPI_MAIL_FROM", user or "epi@eficienciayprecisionindustrial.com")

    saludo = contact_name or (company_name or "")
    precio_txt = f"{final_price_eur:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".") if final_price_eur else ""

    msg = EmailMessage()
    msg["Subject"] = "Su oferta técnica — Eficiencia y Precisión Industrial S.L. (EPi)"
    msg["From"] = mail_from
    msg["To"] = to_email
    cuerpo = (
        f"Estimado/a {saludo},\n\n"
        f"Adjuntamos la propuesta técnica y comercial generada por nuestro asistente EPi "
        f"para su instalación"
        + (f", con un precio final de {precio_txt}." if precio_txt else ".")
        + "\n\nEn caso de aceptación del presupuesto, envíe el pedido oficial a "
        "pedidos@eficienciayprecisionindustrial.com. Si no recibe confirmación de la "
        "recepción de su pedido, es posible que este no se haya tramitado.\n\n"
        "Quedamos a su disposición para cualquier aclaración.\n\n"
        "Un saludo,\nEficiencia y Precisión Industrial, S.L.\nBilbao (Bizkaia)"
    )
    msg.set_content(cuerpo)

    pdf_file = Path(pdf_path)
    if pdf_file.exists():
        msg.add_attachment(
            pdf_file.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=pdf_file.name,
        )

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True
    except Exception:
        # No tumbar la generacion de la oferta si falla el envio de correo.
        return False
