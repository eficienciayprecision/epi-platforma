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
- Metodo de aplicacion actual (pistola manual, valvula automatica, boquilla, rodillo...).
- Cadencia de produccion (piezas/hora o gramos/minuto de adhesivo aplicado).

SI ES DE DOS COMPONENTES (2K):
- Proporcion de mezcla (por ejemplo 1:1, 2:1, 10:1) entre resina y catalizador/endurecedor.
- Pot-life o tiempo de vida util de la mezcla antes de que empiece a curar.
- Si dispone ya de un sistema de mezcla estatica o dinamica, o si mezcla manualmente.
- Cadencia de produccion y si hay paradas frecuentes que puedan dejar adhesivo curado dentro
  de las lineas (riesgo de obstruccion).

REGLAS DE FORMATO:
1. UNA sola pregunta a la vez.
2. Tono profesional, servicial y educativo, igual que el resto de EPi.
3. NUNCA inventes condiciones de la instalacion del cliente.
4. Cuando tengas la informacion suficiente de la rama correspondiente, resume en un parrafo
   claro qué tipo de bomba de dosificacion (peristaltica de precision, de piston, de
   membrana...) y que configuracion recomiendas revisar, y marca el estado como "complete".
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

        return {"status": "incomplete", "message": reply}

    @classmethod
    def _rule_based(cls, user_message: str, history: List[dict]) -> dict:
        """Fallback sin OpenAI: guion fijo segun 1K o 2K detectado en la primera respuesta."""
        msg = user_message.lower()
        is_2k = "2" in msg or "dos componente" in msg or "dos-componente" in msg
        n = len([h for h in history if h.get("role") == "user"])

        questions_1k = [
            "¿Qué tipo de adhesivo de un componente es (poliuretano, silicona, cianoacrilato, hotmelt...) y cómo cura (humedad, calor, UV)?",
            "¿Cómo describiría su viscosidad: fluido, medio, o muy viscoso/pastoso?",
            "¿Cómo lo aplica actualmente: pistola manual, válvula automática, boquilla, rodillo...?",
            "¿Qué cadencia de producción maneja (piezas/hora o gramos/minuto de adhesivo aplicado)?",
        ]
        questions_2k = [
            "¿Qué proporción de mezcla utiliza entre resina y catalizador/endurecedor (por ejemplo 1:1, 2:1, 10:1)?",
            "¿Qué pot-life (tiempo de vida útil de la mezcla antes de empezar a curar) tiene su adhesivo?",
            "¿Dispone ya de un sistema de mezcla estática o dinámica, o mezcla manualmente?",
            "¿Qué cadencia de producción maneja, y tiene paradas frecuentes que puedan dejar adhesivo curado dentro de las líneas?",
        ]
        questions = questions_2k if is_2k else questions_1k

        if n >= len(questions):
            tech = "peristáltica de precisión con cabezal de mezcla dinámica" if is_2k else "de membrana o de pistón, según viscosidad"
            return {
                "status": "complete",
                "message": (
                    f"Con estos datos, una bomba de dosificación {tech} suele ser el punto de "
                    "partida adecuado para su instalación. Un ingeniero de Eficiencia y "
                    "Precisión Industrial revisará el detalle antes de confirmar la solución."
                ),
            }

        return {"status": "incomplete", "message": questions[min(n - 1, len(questions) - 1)]}
