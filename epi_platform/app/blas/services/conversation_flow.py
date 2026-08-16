"""
El "guion" de Blas — maquina de estados de la conversacion comercial
inicial. Es deliberadamente sencilla (basada en reglas, no IA todavia): en
esta primera version el objetivo es capturar un lead completo y avisar al
equipo, no dar ya un presupuesto automatico (eso se conectara mas adelante
con el motor de EPi — ahora mismo viven en el mismo servicio, asi que ese
paso futuro sera mas facil).

Flujo:
  1. Cliente entra en la web, se abre el widget de Blas -> Blas pide el
     telefono.
  2. En cuanto da el telefono, se le manda automaticamente un WhatsApp real
     (plantilla de apertura, obligatoria por politica de Meta) preguntando
     en que le podemos ayudar.
  3. Responda por el widget o por WhatsApp de verdad, Blas sigue preguntando:
     nombre -> aplicacion de la bomba / fluido a controlar.
  4. Despues pide un email para mandar la oferta (o, si no quiere dar
     email, se manda por WhatsApp en su lugar).
  5. Pregunta si quiere dar tambien el email de compras, para mandarles la
     oferta a ellos tambien.
  6. Lead completo -> aviso interno por email al equipo con todos los datos
     y el hilo completo de la conversacion.

La misma funcion handle_inbound_text() se usa tanto si el mensaje llega por
el widget web como si llega por el webhook de WhatsApp real — lo unico que
cambia es el canal, para saber si hay que espejar la respuesta de Blas por
WhatsApp de verdad o solo devolverla al widget (ver _maybe_send_whatsapp).
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.blas.models import Conversation, Message, ConversationState, Channel, DeliveryChannel
from app.blas.services import whatsapp_client, email_service
from app.blas.config import BLAS_INTERNAL_NOTIFY_EMAIL

EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

DECLINE_WORDS = {
    "no", "no gracias", "paso", "no tengo", "prefiero whatsapp", "por aqui",
    "por whatsapp", "whatsapp", "asi esta bien", "nada", "ninguno", "ninguna",
}

BOT_MESSAGES = {
    ConversationState.AWAITING_PHONE: (
        "¡Hola! 👋 Soy Blas, el asistente de Eficiencia y Precisión Industrial. "
        "Para poder ayudarte, dime tu número de teléfono (con prefijo de país, "
        "ej. 34600111222) y seguimos la conversación también por WhatsApp."
    ),
    ConversationState.AWAITING_NEED: (
        "¡Perfecto! Te acabamos de escribir por WhatsApp. Puedes seguir la "
        "conversación aquí mismo o directamente desde tu WhatsApp, como "
        "prefieras. Cuéntame, ¿en qué podemos ayudarte?"
    ),
    ConversationState.AWAITING_NAME: "¿Cómo te llamas?",
    ConversationState.AWAITING_APPLICATION: (
        "Gracias. Para preparar la oferta, cuéntame: ¿qué aplicación tiene la "
        "bomba, o qué fluido necesitas controlar?"
    ),
    ConversationState.AWAITING_DELIVERY_CHOICE: (
        "¿Nos dejas un email para enviarte la oferta? Si lo prefieres, te la "
        "mandamos igualmente por aquí, por WhatsApp."
    ),
    ConversationState.AWAITING_PURCHASING_EMAIL: (
        "¿Quieres pasarme el email del departamento de compras? Se la "
        "mandamos también a ellos."
    ),
    ConversationState.QUALIFIED: (
        "Genial, ya tenemos todo lo necesario. Un ingeniero de Eficiencia y "
        "Precisión Industrial preparará tu oferta y te la haremos llegar en "
        "breve. ¡Gracias por contactar con nosotros!"
    ),
}


def _looks_like_email(text: str) -> Optional[str]:
    m = EMAIL_RE.search(text or "")
    return m.group(0) if m else None


def _is_decline(text: str) -> bool:
    return (text or "").strip().lower() in DECLINE_WORDS


def _log_message(db: Session, conversation: Conversation, direction: str, channel: Channel, body: str) -> None:
    db.add(Message(id=uuid.uuid4(), conversation_id=conversation.id, direction=direction,
                    channel=channel, body=body))


def log_manual_reply(db: Session, conversation: Conversation, body: str) -> None:
    """Para cuando un compañero responde a mano desde la bandeja interna
    (fuera del guion automatico) — registra el mensaje saliente."""
    _log_message(db, conversation, "out", Channel.WHATSAPP, body)
    db.commit()


def _maybe_send_whatsapp(conversation: Conversation, body: str, triggering_channel: Channel) -> None:
    """Manda `body` por WhatsApp de verdad si procede. Nunca lanza excepcion
    hacia arriba (un fallo de WhatsApp no debe romper la respuesta al
    widget) — el error queda en logs, igual que en email_service de EPi."""
    if not conversation.phone:
        return
    if triggering_channel == Channel.WHATSAPP:
        # El cliente acaba de escribir por WhatsApp de verdad -> la ventana
        # de 24h esta abierta, se puede responder con texto libre.
        try:
            whatsapp_client.send_text(conversation.phone, body)
        except Exception as e:
            print(f"AVISO: no se pudo espejar por WhatsApp la respuesta a {conversation.phone}: "
                  f"{type(e).__name__}: {e}")
    elif triggering_channel == Channel.WEB and conversation.whatsapp_window_open:
        # El cliente ya escribio por WhatsApp alguna vez antes (ventana
        # abierta) aunque ahora este contestando por el widget -> tambien
        # se puede espejar.
        try:
            whatsapp_client.send_text(conversation.phone, body)
        except Exception as e:
            print(f"AVISO: no se pudo espejar por WhatsApp la respuesta a {conversation.phone}: "
                  f"{type(e).__name__}: {e}")
    # Si triggering_channel == WEB y la ventana de whatsapp NO esta abierta
    # todavia (el cliente solo ha usado el widget, nunca WhatsApp de
    # verdad), no se intenta mandar nada: Meta lo rechazaria porque solo
    # esta permitida la plantilla de apertura hasta que el cliente escriba.


def get_or_create_web_conversation(db: Session, web_session_id: str) -> Conversation:
    conv = db.query(Conversation).filter(Conversation.web_session_id == web_session_id).first()
    if conv:
        return conv
    conv = Conversation(id=uuid.uuid4(), web_session_id=web_session_id, state=ConversationState.AWAITING_PHONE)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    _log_message(db, conv, "out", Channel.WEB, BOT_MESSAGES[ConversationState.AWAITING_PHONE])
    db.commit()
    return conv


def get_conversation_by_phone(db: Session, phone: str) -> Optional[Conversation]:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return db.query(Conversation).filter(Conversation.phone == digits).first()


def start_whatsapp_conversation(db: Session, phone: str, first_text: str) -> tuple[Conversation, str]:
    """Alguien escribe a Blas por WhatsApp directamente, sin haber pasado
    antes por el widget de la web (p.ej. si en el futuro se publica el
    numero en alguna parte). No hace falta plantilla de apertura porque el
    cliente ya ha escrito el primero — la ventana de 24h ya esta abierta.
    Su primer mensaje se guarda directamente como la necesidad inicial."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    conv = Conversation(
        id=uuid.uuid4(), phone=digits, initial_need=first_text,
        state=ConversationState.AWAITING_NAME, whatsapp_window_open=True,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    _log_message(db, conv, "in", Channel.WHATSAPP, first_text)
    reply = BOT_MESSAGES[ConversationState.AWAITING_NAME]
    _log_message(db, conv, "out", Channel.WHATSAPP, reply)
    db.commit()

    _maybe_send_whatsapp(conv, reply, triggering_channel=Channel.WHATSAPP)
    return conv, reply


def _notify_internal_team(db: Session, conversation: Conversation) -> None:
    if conversation.internal_notified:
        return
    thread = "\n".join(
        f"[{m.created_at:%d/%m %H:%M}] ({'cliente' if m.direction == 'in' else 'Blas'}/{m.channel.value}) {m.body}"
        for m in conversation.messages
    )
    body = (
        f"Nuevo lead cualificado por Blas.\n\n"
        f"Teléfono: {conversation.phone}\n"
        f"Nombre: {conversation.name or '(no indicado)'}\n"
        f"Necesidad inicial: {conversation.initial_need or '(no indicada)'}\n"
        f"Aplicación / fluido a controlar: {conversation.application_or_fluid or '(no indicado)'}\n"
        f"Email de contacto: {conversation.email or '(no dejó email — enviar oferta por WhatsApp)'}\n"
        f"Email de compras: {conversation.purchasing_email or '(no indicado)'}\n"
        f"Canal de entrega de la oferta: "
        f"{conversation.delivery_channel.value if conversation.delivery_channel else '(no decidido)'}\n\n"
        f"--- Conversación completa ---\n{thread}\n"
    )
    sent = email_service.send_internal_lead_notification(
        to_email=BLAS_INTERNAL_NOTIFY_EMAIL,
        subject=f"[Blas] Nuevo lead — {conversation.name or conversation.phone}",
        body_text=body,
    )
    if sent:
        conversation.internal_notified = True
        db.commit()


def handle_phone_submitted(db: Session, conversation: Conversation, phone: str) -> str:
    """El cliente ha dado su telefono en el widget (unico sitio donde se
    pide: por definicion, si llega por WhatsApp real ya tenemos el
    telefono). Dispara el WhatsApp de apertura (plantilla) y avanza el
    estado."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    conversation.phone = digits
    _log_message(db, conversation, "in", Channel.WEB, phone)

    try:
        whatsapp_client.send_opening_template(digits)
        conversation.whatsapp_opened = True
    except Exception as e:
        print(f"AVISO: no se pudo mandar la plantilla de apertura de WhatsApp a {digits}: "
              f"{type(e).__name__}: {e}")

    conversation.state = ConversationState.AWAITING_NEED
    reply = BOT_MESSAGES[ConversationState.AWAITING_NEED]
    _log_message(db, conversation, "out", Channel.WEB, reply)
    db.commit()
    return reply


def handle_inbound_text(db: Session, conversation: Conversation, text: str, channel: Channel) -> str:
    """Avanza la maquina de estados un paso a partir de un mensaje entrante
    (del widget o de WhatsApp real) y devuelve el siguiente mensaje de
    Blas. La respuesta tambien se manda por WhatsApp de verdad cuando
    procede (ver _maybe_send_whatsapp)."""
    if channel == Channel.WHATSAPP:
        conversation.whatsapp_window_open = True

    _log_message(db, conversation, "in", channel, text)
    state = conversation.state

    if state == ConversationState.AWAITING_NEED:
        conversation.initial_need = text
        conversation.state = ConversationState.AWAITING_NAME

    elif state == ConversationState.AWAITING_NAME:
        conversation.name = text.strip()
        conversation.state = ConversationState.AWAITING_APPLICATION

    elif state == ConversationState.AWAITING_APPLICATION:
        conversation.application_or_fluid = text
        conversation.state = ConversationState.AWAITING_DELIVERY_CHOICE

    elif state == ConversationState.AWAITING_DELIVERY_CHOICE:
        email = _looks_like_email(text)
        if email:
            conversation.email = email
            conversation.delivery_channel = DeliveryChannel.EMAIL
        else:
            conversation.delivery_channel = DeliveryChannel.WHATSAPP
        conversation.state = ConversationState.AWAITING_PURCHASING_EMAIL

    elif state == ConversationState.AWAITING_PURCHASING_EMAIL:
        email = _looks_like_email(text)
        if email and not _is_decline(text):
            conversation.purchasing_email = email
        conversation.state = ConversationState.QUALIFIED

    elif state == ConversationState.QUALIFIED:
        # Conversacion ya cualificada; cualquier mensaje adicional se
        # guarda (arriba, en _log_message) pero no cambia el estado — un
        # ingeniero sigue la conversacion a partir de aqui desde la
        # bandeja interna.
        db.commit()
        return "Un ingeniero revisará tu consulta y te contactará en breve. ¡Gracias!"

    else:  # AWAITING_PHONE — no deberia llegar texto libre en este estado por WhatsApp
        db.commit()
        return BOT_MESSAGES[ConversationState.AWAITING_PHONE]

    reply = BOT_MESSAGES[conversation.state]
    _log_message(db, conversation, "out", channel, reply)
    db.commit()

    _maybe_send_whatsapp(conversation, reply, triggering_channel=channel)

    if conversation.state == ConversationState.QUALIFIED:
        _notify_internal_team(db, conversation)

    return reply
