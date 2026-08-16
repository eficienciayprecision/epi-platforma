"""
Router de Blas — asistente comercial por WhatsApp, montado dentro de la
misma app FastAPI que EPi (ver app/main.py: `app.include_router(blas_router)`).

Todas las rutas cuelgan de /blas para no chocar con las de EPi:
  GET  /blas                                    -> pagina de demo del widget
  GET  /blas/widget.js                          -> script embebible
  GET  /blas/inbox                               -> bandeja interna
  POST /blas/api/v1/widget/start                -> abre/recupera conversacion del widget
  POST /blas/api/v1/widget/message               -> siguiente mensaje del cliente (widget)
  GET/POST /blas/webhook/whatsapp                -> webhook de Meta (verificacion + mensajes entrantes)
  GET  /blas/api/internal/conversations          -> lista (bandeja interna)
  GET  /blas/api/internal/conversations/{id}     -> detalle
  POST /blas/api/internal/conversations/{id}/reply -> responder a mano

Comparte base de datos (Base/engine/get_db) con EPi — sus tablas
(`conversations`, `messages`) se crean junto a las de EPi en el
Base.metadata.create_all(bind=engine) de app/main.py.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.blas.config import WHATSAPP_VERIFY_TOKEN, BLAS_INTERNAL_TOKEN
from app.blas.models import Conversation, ConversationState, Channel
from app.blas.services import conversation_flow, whatsapp_client

router = APIRouter(prefix="/blas", tags=["Blas"])

BLAS_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "blas"


# ---------------------------------------------------------------------------
# Paginas / assets
# ---------------------------------------------------------------------------

@router.get("/health")
def blas_health():
    return {"status": "ok", "system": "Blas", "version": "0.1.0"}


@router.get("")
@router.get("/")
def blas_demo():
    demo = BLAS_FRONTEND_DIR / "demo.html"
    if demo.exists():
        return FileResponse(demo)
    return {"message": "Blas API", "widget": "/blas/widget.js", "inbox": "/blas/inbox"}


@router.get("/widget.js")
def blas_widget_js():
    return FileResponse(BLAS_FRONTEND_DIR / "widget.js", media_type="application/javascript")


@router.get("/inbox")
def blas_inbox_page():
    return FileResponse(BLAS_FRONTEND_DIR / "inbox.html")


# ---------------------------------------------------------------------------
# Widget web — cliente entra en la web de la empresa
# ---------------------------------------------------------------------------

class WidgetStartRequest(BaseModel):
    web_session_id: str


class WidgetMessageRequest(BaseModel):
    web_session_id: str
    text: str


def _messages_payload(conversation: Conversation) -> list[dict]:
    return [
        {"direction": m.direction, "channel": m.channel.value, "body": m.body,
         "created_at": m.created_at.isoformat() if m.created_at else None}
        for m in conversation.messages
    ]


@router.post("/api/v1/widget/start")
def blas_widget_start(payload: WidgetStartRequest, db: Session = Depends(get_db)):
    """Se llama al abrir el widget por primera vez (o al recargar la
    pagina). web_session_id lo genera y guarda el propio widget.js en el
    navegador (localStorage), para poder recuperar la conversacion."""
    conv = conversation_flow.get_or_create_web_conversation(db, payload.web_session_id)
    return {"state": conv.state.value, "messages": _messages_payload(conv)}


@router.post("/api/v1/widget/message")
def blas_widget_message(payload: WidgetMessageRequest, db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.web_session_id == payload.web_session_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversacion no encontrada — llama antes a /blas/api/v1/widget/start")

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Mensaje vacio")

    if conv.state == ConversationState.AWAITING_PHONE:
        reply = conversation_flow.handle_phone_submitted(db, conv, text)
    else:
        reply = conversation_flow.handle_inbound_text(db, conv, text, Channel.WEB)

    db.refresh(conv)
    return {"state": conv.state.value, "reply": reply, "messages": _messages_payload(conv)}


# ---------------------------------------------------------------------------
# Webhook de WhatsApp (Meta) — conversacion real por WhatsApp
# ---------------------------------------------------------------------------

@router.get("/webhook/whatsapp")
def blas_whatsapp_verify(request: Request):
    """Meta llama a esto UNA VEZ al configurar el webhook en Business
    Manager, para comprobar que el servidor es tuyo. Tiene que devolver
    exactamente el `hub.challenge` si el `hub.verify_token` coincide con
    WHATSAPP_VERIFY_TOKEN (el mismo valor que pones en el panel de Meta)."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    raise HTTPException(status_code=403, detail="Verify token incorrecto")


@router.post("/webhook/whatsapp")
async def blas_whatsapp_incoming(request: Request, db: Session = Depends(get_db)):
    """Meta manda aqui cada mensaje entrante (y tambien "status" de
    entrega/lectura, que se ignoran). Siempre se devuelve 200 rapido —
    Meta reintenta y acaba desactivando el webhook si tarda o falla."""
    payload = await request.json()
    parsed = whatsapp_client.parse_inbound_webhook(payload)
    if not parsed or not parsed.get("phone"):
        return JSONResponse({"status": "ignored"})

    phone, text = parsed["phone"], parsed.get("text")
    if not text:
        # de momento Blas solo entiende texto en esta primera version
        return JSONResponse({"status": "ignored_non_text"})

    conv = conversation_flow.get_conversation_by_phone(db, phone)
    if conv:
        conversation_flow.handle_inbound_text(db, conv, text, Channel.WHATSAPP)
    else:
        conversation_flow.start_whatsapp_conversation(db, phone, text)

    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Bandeja interna — ver y responder conversaciones
# ---------------------------------------------------------------------------

def _check_internal_token(x_blas_token: str = Header(default="")) -> None:
    if not BLAS_INTERNAL_TOKEN or x_blas_token != BLAS_INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Token interno incorrecto")


@router.get("/api/internal/conversations")
def blas_list_conversations(db: Session = Depends(get_db), _=Depends(_check_internal_token)):
    convs = db.query(Conversation).order_by(Conversation.updated_at.desc()).limit(200).all()
    return [
        {
            "id": str(c.id), "phone": c.phone, "name": c.name, "state": c.state.value,
            "application_or_fluid": c.application_or_fluid, "email": c.email,
            "purchasing_email": c.purchasing_email,
            "delivery_channel": c.delivery_channel.value if c.delivery_channel else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in convs
    ]


@router.get("/api/internal/conversations/{conversation_id}")
def blas_get_conversation(conversation_id: str, db: Session = Depends(get_db), _=Depends(_check_internal_token)):
    conv = db.query(Conversation).filter(Conversation.id == uuid.UUID(conversation_id)).first()
    if not conv:
        raise HTTPException(status_code=404, detail="No encontrada")
    return {
        "id": str(conv.id), "phone": conv.phone, "name": conv.name, "state": conv.state.value,
        "initial_need": conv.initial_need, "application_or_fluid": conv.application_or_fluid,
        "email": conv.email, "purchasing_email": conv.purchasing_email,
        "delivery_channel": conv.delivery_channel.value if conv.delivery_channel else None,
        "whatsapp_window_open": conv.whatsapp_window_open,
        "messages": _messages_payload(conv),
    }


class InternalReplyRequest(BaseModel):
    text: str


@router.post("/api/internal/conversations/{conversation_id}/reply")
def blas_reply_to_conversation(conversation_id: str, payload: InternalReplyRequest,
                                db: Session = Depends(get_db), _=Depends(_check_internal_token)):
    """Para que un compañero conteste a mano desde la bandeja interna
    (fuera ya del guion automatico de Blas). Solo funciona si la ventana de
    24h de WhatsApp sigue abierta; si no, Meta lo rechazara y hay que
    volver a mandar una plantilla aprobada (no implementado todavia)."""
    conv = db.query(Conversation).filter(Conversation.id == uuid.UUID(conversation_id)).first()
    if not conv:
        raise HTTPException(status_code=404, detail="No encontrada")
    if not conv.phone:
        raise HTTPException(status_code=400, detail="Esta conversacion todavia no tiene telefono")

    try:
        whatsapp_client.send_text(conv.phone, payload.text)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"No se pudo enviar por WhatsApp: {e}")

    conversation_flow.log_manual_reply(db, conv, payload.text)
    return {"status": "sent"}
