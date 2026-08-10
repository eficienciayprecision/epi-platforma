"""Agente de entrevista especializado en instalaciones de dosificacion de adhesivo.

Flujo especifico para clientes que llegan buscando mejorar una instalacion de
aplicacion/dosificacion de adhesivo, en vez de una instalacion generica de
bombeo. La primera pregunta distingue adhesivo de un componente (1K) o de
dos componentes (2K), porque determina por completo el resto de variables
relevantes (proporcion de mezcla, pot-life, sistema de mezcla estatica, etc.).

NOTA: solo la primera pregunta (1K vs 2K) esta completamente definida por el
cliente. El resto de preguntas de cada rama son un punto de partida razonable
a partir del conocimiento de dosificacion de precision de EPi (ver Dossier de
Especificaciones, seccion "Bombas Peristalticas... dosificacion de alta
precision") y deben revisarse y ampliarse con el promotor antes de produccion.
"""
from __future__ import annotations

import os
from typing import List, Optional

try:
    from openai import OpenAI
    _client = OpenAI() if os.getenv("OPENAI_API_KEY") else None
except Exception:
    _client = None


SYSTEM_PROMPT = """
Eres EPi, un ingeniero tecnico experto en instalaciones de dosificacion y aplicacion de
adhesivos industriales, en 'Eficiencia y Precision Industrial S.L.'.

El cliente quiere mejorar una instalacion EXISTENTE de aplicacion de adhesivo. Tu primera
pregunta, SIEMPRE, debe ser: si el adhesivo que utiliza es de UN componente (1K) o de DOS
componentes (2K), porque condiciona todo lo demas.

A partir de la respuesta, sigue estas ramas (una pregunta a la vez, sin adelantarte):

SI ES DE UN COMPONENTE (1K):
- Tipo de adhesivo (poliuretano, silicona, cianoacrilato, hotmelt, etc.) y si cura por
  humedad, por calor o por UV.
- Viscosidad aproximada (fluido, medio, muy viscoso/pastoso).
- Cadencia de produccion (piezas/hora o gramos/minuto de adhesivo aplicado).

SI ES DE DOS COMPONENTES (2K):
- Proporcion de mezcla (por ejemplo 1:1, 2:1, 10:1) entre resina y catalizador/endurecedor.
- Viscosidad aproximada de CADA componente (resina y catalizador/endurecedor) por separado.
- Pot-life o tiempo de vida util de la mezcla antes de que empiece a curar.
- Si dispone ya de un sistema de mezcla estatica o dinamica, o si mezcla manualmente.
- Cadencia de produccion y si hay paradas frecuentes que puedan dejar adhesivo curado dentro
  de las lineas (riesgo de obstruccion).

PREGUNTAS COMUNES A 1K Y 2K (preguntar SIEMPRE, en ambos casos, ademas de las anteriores):
- En que formato le suministran el material (lo habitual es bidon de 20 o 200 litros).
  Indicar que, en el momento del pedido, EPi necesitara el DIAMETRO EXACTO del bidon (no basta
  con el formato/volumen) para dimensionar correctamente el elevador de bidon.
- Cuantos METROS DE MANGUERA hacen falta entre el elevador de bidon y el punto de aplicacion.
- Si la aplicacion va a ser MANUAL o AUTOMATICA.
- SOLO SI la aplicacion es automatica: si necesita fotocelula y electrovalvula (se cogen del
  catalogo de repuestos de EPi).

QUE PASA AL TERMINAR (MUY IMPORTANTE, es diferente segun 1K o 2K):
- SI ES 1K: EPi genera una oferta con precio al momento, con cada elemento explicado
  (referencia y precio): bomba de piston (de clapetas/chop-check con relacion 23:1 a 46:1 si
  el adhesivo es muy viscoso/pastoso; de bolas normal si no), elevador de bidon, manguera
  (segun los metros indicados), y la pistola manual de extrusion Walther Pilot si la
  aplicacion es manual, o la fotocelula/electrovalvula si es automatica. Ademas incluye un
  croquis esquematico de la instalacion.
- SI ES 2K: NO se genera una oferta con precio automatica. Se recogen todos los datos y se
  envia un correo al cliente confirmando que un ingeniero de Eficiencia y Precision Industrial
  se pondra en contacto a la mayor brevedad posible para comentar los datos y hacerle llegar
  la oferta.

REGLAS DE FORMATO:
1. UNA sola pregunta a la vez.
2. Tono profesional, servicial y educativo, igual que el resto de EPi.
3. NUNCA inventes condiciones de la instalacion del cliente.
4. Cuando tengas toda la informacion, marca el estado como "complete" con un resumen breve.
"""


class AdhesiveAgent:
    SYSTEM_PROMPT = SYSTEM_PROMPT

    FIRST_QUESTION = (
        "Entendido, vamos a revisar su instalación de adhesivo. Antes de nada: "
        "¿el adhesivo que utiliza es de un componente (1K) o de dos componentes (2K)?"
    )

    @classmethod
    def process_message(cls, user_message: str, chat_history: Optional[List[dict]] = None) -> dict:
        history = chat_history or []

        # Primer turno: se lanza siempre la pregunta 1K/2K, sin gastar llamada a LLM.
        if not history:
            return {"status": "incomplete", "message": cls.FIRST_QUESTION}

        if _client is None:
            return cls._rule_based(user_message, history)

        messages = [{"role": "system", "content": cls.SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = _client.chat.completions.create(
                model=os.getenv("EPI_LLM_MODEL", "gpt-4o-mini"),
                messages=messages,
                temperature=0.2,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            return {"status": "error", "message": f"Error LLM: {e}"}

        # Modo LLM: extraccion basica (best-effort) igual que en rule-based,
        # para poder generar la oferta 1K o el correo 2K sin otra llamada.
        data = cls._extract_data(user_message, history)
        return {"status": "incomplete", "message": reply, "data": data}

    @classmethod
    def _extract_data(cls, user_message: str, history: List[dict]) -> dict:
        """Extrae por palabras clave los datos estructurados de la conversacion
        hasta ahora: 1K/2K, aplicacion manual/automatica, tamaño de bidon en
        litros, si necesita fotocelula/electrovalvula. Best-effort — no
        sustituye al juicio de un ingeniero, ver notas en el modulo."""
        import re
        all_user_texts = [h.get("content", "") for h in history if h.get("role") == "user"]
        if not all_user_texts:
            all_user_texts = [user_message]
        joined = " ".join(all_user_texts).lower()

        first_answer = all_user_texts[0].lower()
        is_2k = "2" in first_answer or "dos componente" in first_answer or "dos-componente" in first_answer

        is_automatic = "autom" in joined or "robot" in joined
        is_manual = ("manual" in joined) and not is_automatic

        m = re.search(r'(\d+)\s*(?:litro|l\b)', joined)
        drum_liters = int(m.group(1)) if m else None

        needs_photocell = bool(re.search(r'fotoc[eé]lula', joined)) and not re.search(r'\bno\b[^.]{0,15}fotoc[eé]lula', joined)
        needs_solenoid = bool(re.search(r'electrov[aá]lvula', joined)) and not re.search(r'\bno\b[^.]{0,15}electrov[aá]lvula', joined)
        is_viscous = bool(re.search(r'muy viscos|pastos|pasta', joined))

        return {
            "is_2k": is_2k,
            "application_type": "automatica" if is_automatic else ("manual" if is_manual else None),
            "is_viscous": is_viscous,
            "drum_liters": drum_liters,
            "needs_photocell": needs_photocell,
            "needs_solenoid": needs_solenoid,
            "raw_answers": all_user_texts,
        }

    @classmethod
    def _rule_based(cls, user_message: str, history: List[dict]) -> dict:
        """Fallback sin OpenAI: guion fijo segun 1K o 2K detectado en la primera
        respuesta, con las preguntas comunes de formato de suministro y tipo de
        aplicacion (manual/automatica -> fotocelula/electrovalvula si aplica).

        IMPORTANTE: el frontend ya incluye el mensaje actual como ultimo
        elemento de `history` (lo añade antes de llamar al endpoint) — no hay
        que volver a añadirlo, o las preguntas se desajustan una posicion."""
        all_user_texts = [h.get("content", "") for h in history if h.get("role") == "user"]
        if not all_user_texts:
            all_user_texts = [user_message]

        first_answer = all_user_texts[0].lower()
        is_2k = "2" in first_answer or "dos componente" in first_answer or "dos-componente" in first_answer

        specific_1k = [
            "¿Qué tipo de adhesivo de un componente es (poliuretano, silicona, cianoacrilato, hotmelt...) y cómo cura (humedad, calor, UV)?",
            "¿Cómo describiría su viscosidad: fluido, medio, o muy viscoso/pastoso?",
        ]
        specific_2k = [
            "¿Qué proporción de mezcla utiliza entre resina y catalizador/endurecedor (por ejemplo 1:1, 2:1, 10:1)?",
            "¿Qué viscosidad aproximada tiene cada componente (resina y catalizador/endurecedor)?",
            "¿Qué pot-life (tiempo de vida útil de la mezcla antes de empezar a curar) tiene su adhesivo?",
            "¿Dispone ya de un sistema de mezcla estática o dinámica, o mezcla manualmente?",
        ]
        specific = specific_2k if is_2k else specific_1k

        common_pre = [
            "¿La aplicación va a ser manual (pistola manual) o automática (válvula/aplicador automático)?",
            "¿En qué formato le suministran el material (lo habitual es bidón de 20 o 200 litros)? "
            "Tenga en cuenta que, en el momento del pedido, necesitaremos el diámetro exacto del "
            "bidón para dimensionar bien el elevador.",
            "¿Cuántos metros de manguera hacen falta entre el elevador de bidón y el punto de aplicación?",
        ]
        common_post = ["¿Qué cadencia de producción maneja (piezas/hora o gramos/minuto de adhesivo aplicado)?"]

        app_question_idx = 1 + len(specific)
        application_answer = all_user_texts[app_question_idx] if len(all_user_texts) > app_question_idx else ""
        is_automatic = any(k in application_answer.lower() for k in ("autom", "robot"))

        full_questions = specific + common_pre
        if is_automatic:
            full_questions = full_questions + [
                "Para la aplicación automática: ¿necesita fotocélula (detección de pieza / disparo del ciclo)?",
                "Y también para la aplicación automática: ¿necesita electroválvula (accionamiento neumático del aplicador)?",
            ]
        full_questions = full_questions + common_post

        n = len(all_user_texts) - 1

        if n >= len(full_questions):
            # Construir el dict de datos con las respuestas EXACTAS por
            # posicion (mas fiable que buscar palabras clave sueltas: la
            # respuesta a "¿necesita fotocelula?" suele ser solo "Si"/"No",
            # sin la palabra "fotocelula" dentro).
            drum_liters = None
            for txt in all_user_texts:
                import re as _re
                m = _re.search(r'(\d+)\s*(?:litro|l\b)', txt.lower())
                if m:
                    drum_liters = int(m.group(1))
                    break

            # app_question_idx = indice de la respuesta manual/auto.
            # +1 = formato de suministro, +2 = metros de manguera,
            # +3 = fotocelula, +4 = electrovalvula (solo si automatica).
            manguera_idx = app_question_idx + 2
            hose_meters = None
            if len(all_user_texts) > manguera_idx:
                import re as _re
                m = _re.search(r'(\d+(?:[.,]\d+)?)', all_user_texts[manguera_idx])
                if m:
                    hose_meters = float(m.group(1).replace(",", "."))

            needs_photocell = False
            needs_solenoid = False
            if is_automatic:
                photocell_idx = app_question_idx + 3
                solenoid_idx = app_question_idx + 4
                if len(all_user_texts) > photocell_idx:
                    needs_photocell = any(k in all_user_texts[photocell_idx].lower() for k in ("sí", "si", "yes", "necesito", "hace falta"))
                if len(all_user_texts) > solenoid_idx:
                    needs_solenoid = any(k in all_user_texts[solenoid_idx].lower() for k in ("sí", "si", "yes", "necesito", "hace falta"))

            # Viscosidad: solo se pregunta explicitamente en la rama 1K
            # (specific_1k[1], indice 2 en all_user_texts). Si es "muy
            # viscoso/pastoso" hace falta bomba de clapetas (chop-check),
            # no la de bolas estandar — ver seleccion en app/main.py.
            is_viscous = False
            if not is_2k and len(all_user_texts) > 2:
                is_viscous = any(k in all_user_texts[2].lower() for k in ("muy viscos", "pastos", "pasta"))

            data = {
                "is_2k": is_2k,
                "application_type": "automatica" if is_automatic else "manual",
                "is_viscous": is_viscous,
                "drum_liters": drum_liters,
                "hose_meters": hose_meters,
                "needs_photocell": needs_photocell,
                "needs_solenoid": needs_solenoid,
                "raw_answers": all_user_texts,
            }
            if is_2k:
                message = (
                    "Datos recogidos. Como es un adhesivo de dos componentes, un ingeniero de "
                    "Eficiencia y Precisión Industrial revisará el detalle antes de proponer "
                    "equipo — no generamos una oferta automática con precio para 2K. Indique su "
                    "email en \"Tus datos\" y pulse el botón para que le enviemos la confirmación."
                )
            else:
                equipo = ["bomba de pistón" + (" de clapetas (chop-check)" if is_viscous else ""), "manguera"]
                if is_automatic:
                    equipo.append("fotocélula y electroválvula (si las necesita)")
                else:
                    equipo.append("pistola manual de extrusión Walther Pilot")
                equipo.append("elevador de bidón (según el tamaño del bidón)")
                message = (
                    "Datos recogidos. Podemos generarle ya una oferta con precio para el equipo "
                    f"de aplicación ({', '.join(equipo)}), con referencia y precio de cada "
                    "elemento y un croquis de la instalación — el diámetro exacto del bidón se "
                    "confirmará en el pedido. Pulse el botón para generarla."
                )
            return {"status": "complete", "message": message, "data": data}

        return {"status": "incomplete", "message": full_questions[min(n, len(full_questions) - 1)]}
