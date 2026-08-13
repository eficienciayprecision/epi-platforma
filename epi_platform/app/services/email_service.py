"""Envio automatico de la oferta (PDF) al email del contacto.

Dos transportes posibles, en este orden de prioridad:

1) RESEND (API HTTP) — si EPI_RESEND_API_KEY esta configurada. Recomendado:
   no usa puertos SMTP (que Render bloquea en el plan gratuito), y con
   dominio verificado (SPF/DKIM en el panel de Resend) se puede enviar
   "como" epi@eficienciayprecisionindustrial.com sin exponer ninguna
   contraseña de un buzon real.
     EPI_RESEND_API_KEY, EPI_MAIL_FROM

2) SMTP clasico (Arsys, Gmail, Microsoft365...) — si no hay
   EPI_RESEND_API_KEY pero si EPI_SMTP_HOST. Se mantiene por si se prefiere
   subir de plan en Render (los planes de pago no bloquean SMTP saliente)
   en vez de depender de un proveedor externo.
     EPI_SMTP_HOST, EPI_SMTP_PORT, EPI_SMTP_USER, EPI_SMTP_PASSWORD,
     EPI_SMTP_USE_TLS (true/false), EPI_MAIL_FROM

Si no hay ninguno de los dos configurado, el envio se omite (util en
desarrollo/local) y se devuelve sent=False, dejando aviso en logs.

IMPORTANTE sobre EPI_MAIL_FROM=epi@eficienciayprecisionindustrial.com:
con SMTP, la mayoria de servidores exigen que el usuario autenticado
(EPI_SMTP_USER) coincida con el remitente del "From", o que este
autorizado explicitamente a enviar en su nombre (alias/"Send As"). Esto NO
requiere dar a EPi acceso a leer el correo de esa cuenta (bandeja de
entrada, contactos, etc.) — solo una credencial de ENVIO para esa
direccion. Con Resend esto se resuelve verificando el dominio una vez.
"""
from __future__ import annotations

import base64
import os
import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

import httpx

RESEND_API_URL = "https://api.resend.com/emails"


def _send_smtp_with_retry(host: str, port: int, use_tls: bool, user: Optional[str],
                           password: Optional[str], msg: EmailMessage,
                           attempts: int = 2, timeout: int = 20, retry_wait: int = 3) -> None:
    """La conexion SMTP directa a veces se queda colgada en vez de fallar al
    momento (comprobado con datos reales en Render) — timeout generoso y un
    reintento. 2 intentos x 20s deja un peor caso de ~43s de espera al
    generar la oferta."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with smtplib.SMTP(host, port, timeout=timeout) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
            return
        except Exception as e:
            last_error = e
            print(f"  intento {attempt}/{attempts} fallido (SMTP): {type(e).__name__}: {e}")
            if attempt < attempts:
                time.sleep(retry_wait)
    raise last_error


def _send_via_resend(api_key: str, to_email: str, subject: str, body_text: str,
                      mail_from: str, pdf_path: Optional[str],
                      attempts: int = 2, timeout: int = 20, retry_wait: int = 3) -> None:
    payload = {
        "from": mail_from,
        "to": [to_email],
        "subject": subject,
        "text": body_text,
    }
    if pdf_path:
        pdf_file = Path(pdf_path)
        if pdf_file.exists():
            payload["attachments"] = [{
                "filename": pdf_file.name,
                "content": base64.b64encode(pdf_file.read_bytes()).decode("ascii"),
            }]

    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            resp = httpx.post(
                RESEND_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return
        except Exception as e:
            last_error = e
            print(f"  intento {attempt}/{attempts} fallido (Resend): {type(e).__name__}: {e}")
            if attempt < attempts:
                time.sleep(retry_wait)
    raise last_error


def _send_email(to_email: str, subject: str, body_text: str, pdf_path: Optional[str] = None) -> bool:
    """Punto unico de envio: intenta Resend si esta configurado, si no cae a
    SMTP. Devuelve True/False y SIEMPRE deja constancia en logs del motivo
    exacto si falla (nunca falla en silencio)."""
    mail_from = os.getenv("EPI_MAIL_FROM", "epi@eficienciayprecisionindustrial.com")
    resend_key = os.getenv("EPI_RESEND_API_KEY")

    if resend_key:
        try:
            _send_via_resend(resend_key, to_email, subject, body_text, mail_from, pdf_path)
            print(f"Email enviado correctamente a {to_email} (Resend)")
            return True
        except Exception as e:
            print(f"ERROR enviando email a {to_email} via Resend (tras varios intentos): {type(e).__name__}: {e}")
            return False

    host = os.getenv("EPI_SMTP_HOST")
    if not host:
        print("AVISO: no hay EPI_RESEND_API_KEY ni EPI_SMTP_HOST configuradas — no se envia el email (solo se genera el PDF).")
        return False

    port = int(os.getenv("EPI_SMTP_PORT", "587"))
    user = os.getenv("EPI_SMTP_USER")
    password = os.getenv("EPI_SMTP_PASSWORD")
    use_tls = os.getenv("EPI_SMTP_USE_TLS", "true").lower() == "true"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = to_email
    msg.set_content(body_text)

    if pdf_path:
        pdf_file = Path(pdf_path)
        if pdf_file.exists():
            msg.add_attachment(
                pdf_file.read_bytes(), maintype="application", subtype="pdf", filename=pdf_file.name,
            )

    try:
        _send_smtp_with_retry(host, port, use_tls, user, password, msg)
        print(f"Email enviado correctamente a {to_email} (SMTP)")
        return True
    except Exception as e:
        print(f"ERROR enviando email a {to_email} via SMTP (tras varios intentos): {type(e).__name__}: {e}")
        return False


def send_offer_email(
    to_email: str,
    contact_name: Optional[str],
    company_name: Optional[str],
    pdf_path: str,
    final_price_eur: Optional[float] = None,
) -> bool:
    saludo = contact_name or (company_name or "")
    precio_txt = f"{final_price_eur:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".") if final_price_eur else ""

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
    return _send_email(
        to_email=to_email,
        subject="Su oferta técnica — Eficiencia y Precisión Industrial S.L. (EPi)",
        body_text=cuerpo,
        pdf_path=pdf_path,
    )


def send_internal_report_email(
    to_email: str,
    client_id: str,
    pdf_path: str,
    final_price_eur: Optional[float] = None,
) -> bool:
    """Copia interna del Informe Tecnico (con el razonamiento de tecnologia,
    compatibilidad quimica y de donde ha sacado cada componente) a una
    direccion interna, cada vez que EPi genera un presupuesto completo."""
    precio_txt = f"{final_price_eur:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".") if final_price_eur else ""

    cuerpo = (
        f"Informe interno del presupuesto {client_id}"
        + (f" (precio final {precio_txt})" if precio_txt else "")
        + ".\n\nIncluye el razonamiento de tecnologia de bomba, la comprobacion de "
        "compatibilidad quimica, y de donde ha sacado EPi cada componente/material "
        "de la oferta. Documento de uso interno — no reenviar al cliente.\n"
    )
    return _send_email(
        to_email=to_email,
        subject=f"[Informe interno] Presupuesto {client_id}",
        body_text=cuerpo,
        pdf_path=pdf_path,
    )


def send_adhesive_followup_email(
    to_email: str,
    contact_name: Optional[str],
    company_name: Optional[str],
    raw_answers: list,
) -> bool:
    """Adhesivo de 2 componentes: no se genera oferta con precio automatica.
    Se envia al cliente un correo confirmando que un ingeniero de EPI le
    contactara, con los datos recogidos como referencia."""
    saludo = contact_name or (company_name or "")
    datos_txt = "\n".join(f"- {a}" for a in raw_answers)

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
    return _send_email(
        to_email=to_email,
        subject="Su consulta de dosificación de adhesivo — Eficiencia y Precisión Industrial (EPi)",
        body_text=cuerpo,
    )
