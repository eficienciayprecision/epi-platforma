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
        # FIX — antes esto era silencioso (sin print): si EPI_SMTP_HOST no
        # estaba bien puesta en Render, "PDF generado sin email" pasaba sin
        # dejar ningun rastro en los logs, indistinguible de un fallo real
        # de envio. Ahora queda constancia igual que en el resto de errores.
        print("AVISO: EPI_SMTP_HOST no esta configurada — no se envia el email de oferta (solo se genera el PDF).")
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
        print(f"Email de oferta enviado correctamente a {to_email}")
        return True
    except Exception as e:
        # No tumbar la generacion de la oferta si falla el envio de correo,
        # pero SI dejar constancia en los logs del motivo exacto del fallo
        # (antes este bloque lo atrapaba en silencio y era invisible).
        print(f"ERROR enviando email de oferta a {to_email}: {type(e).__name__}: {e}")
        return False


def send_internal_report_email(
    to_email: str,
    client_id: str,
    pdf_path: str,
    final_price_eur: Optional[float] = None,
) -> bool:
    """NUEVO — copia interna del Informe Tecnico (el PDF de uso interno, con
    el razonamiento de tecnologia, compatibilidad quimica y de donde ha
    sacado cada componente) a una direccion interna, cada vez que EPi genera
    un presupuesto completo. Independiente de si el cliente dejo su email o
    no — esto es para seguimiento interno, no para el cliente."""
    host = os.getenv("EPI_SMTP_HOST")
    if not host:
        print("AVISO: EPI_SMTP_HOST no esta configurada — no se envia el informe interno.")
        return False

    port = int(os.getenv("EPI_SMTP_PORT", "587"))
    user = os.getenv("EPI_SMTP_USER")
    password = os.getenv("EPI_SMTP_PASSWORD")
    use_tls = os.getenv("EPI_SMTP_USE_TLS", "true").lower() == "true"
    mail_from = os.getenv("EPI_MAIL_FROM", user or "epi@eficienciayprecisionindustrial.com")

    precio_txt = f"{final_price_eur:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".") if final_price_eur else ""

    msg = EmailMessage()
    msg["Subject"] = f"[Informe interno] Presupuesto {client_id}"
    msg["From"] = mail_from
    msg["To"] = to_email
    cuerpo = (
        f"Informe interno del presupuesto {client_id}"
        + (f" (precio final {precio_txt})" if precio_txt else "")
        + ".\n\nIncluye el razonamiento de tecnologia de bomba, la comprobacion de "
        "compatibilidad quimica, y de donde ha sacado EPi cada componente/material "
        "de la oferta. Documento de uso interno — no reenviar al cliente.\n"
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
        print(f"Email de informe interno enviado correctamente a {to_email}")
        return True
    except Exception as e:
        print(f"ERROR enviando email de informe interno a {to_email}: {type(e).__name__}: {e}")
        return False


def send_adhesive_followup_email(
    to_email: str,
    contact_name: Optional[str],
    company_name: Optional[str],
    raw_answers: list,
) -> bool:
    """NUEVO — adhesivo de 2 componentes: no se genera oferta con precio
    automatica. Se envia al cliente un correo confirmando que un ingeniero
    de EPI le contactara, con los datos recogidos como referencia."""
    host = os.getenv("EPI_SMTP_HOST")
    if not host:
        print("AVISO: EPI_SMTP_HOST no esta configurada — no se envia el correo de seguimiento 2K.")
        return False

    port = int(os.getenv("EPI_SMTP_PORT", "587"))
    user = os.getenv("EPI_SMTP_USER")
    password = os.getenv("EPI_SMTP_PASSWORD")
    use_tls = os.getenv("EPI_SMTP_USE_TLS", "true").lower() == "true"
    mail_from = os.getenv("EPI_MAIL_FROM", user or "epi@eficienciayprecisionindustrial.com")

    saludo = contact_name or (company_name or "")
    datos_txt = "\n".join(f"- {a}" for a in raw_answers)

    msg = EmailMessage()
    msg["Subject"] = "Su consulta de dosificación de adhesivo — Eficiencia y Precisión Industrial (EPi)"
    msg["From"] = mail_from
    msg["To"] = to_email
    cuerpo = (
        f"Estimado/a {saludo},\n\n"
        "Gracias por su consulta sobre su instalación de dosificación de adhesivo de dos "
        "componentes. Al tratarse de una aplicación 2K, un ingeniero de Eficiencia y "
        "Precisión Industrial S.L. se pondrá en contacto con usted a la mayor brevedad "
        "posible para comentar los datos y hacerle llegar la oferta.\n\n"
        "Datos recogidos en la consulta:\n" + datos_txt + "\n\n"
        "Quedamos a su disposición para cualquier aclaración.\n\n"
        "Un saludo,\nEficiencia y Precisión Industrial, S.L.\nBilbao (Bizkaia)"
    )
    msg.set_content(cuerpo)

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        print(f"Email de seguimiento adhesivo 2K enviado correctamente a {to_email}")
        return True
    except Exception as e:
        print(f"ERROR enviando email de seguimiento adhesivo 2K a {to_email}: {type(e).__name__}: {e}")
        return False
