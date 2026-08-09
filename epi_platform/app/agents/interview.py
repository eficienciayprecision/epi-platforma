"""Agente conversacional de entrevista tecnica."""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional

from app.schemas.epi_schemas import HydraulicCalculationRequest

# OpenAI opcional: si no hay API key, usa modo regla (sin LLM)
try:
    from openai import OpenAI
    _client = OpenAI() if os.getenv("OPENAI_API_KEY") else None
except Exception:
    _client = None


SYSTEM_PROMPT = """
Eres EPi, un ingeniero tecnico de ventas senior en 'Eficiencia y Precision Industrial S.L.'.
Tu objetivo es obtener 6 bloques de variables clave de un cliente para dimensionar una bomba
industrial, adaptandote a su nivel tecnico.

LOS 6 BLOQUES OBJETIVO:
1. Caudal deseado (flow_m3h) en m3/h
2. Altura estatica a vencer (static_head_m) en m
3. Longitud de la tuberia (length_m) en m
4. Diametro interior de la tuberia (diameter_mm) en mm
5. Propiedades del fluido -> density_kg_m3 y viscosity_cp (tambien captura fluid_name)
6. Naturaleza del fluido/proceso, para elegir la TECNOLOGIA de bomba correcta:
   - has_solids: ¿el fluido lleva solidos en suspension (particulas, fibras...)?
   - is_abrasive: ¿es abrasivo (lodos, arenas, particulas duras)?
   - is_shear_sensitive: ¿es un fluido delicado que no debe agitarse/dañarse mecanicamente
     (p.ej. biologico, alimentario fragil, con floculos)?
   - requires_continuous_flow: ¿necesita un caudal continuo/sin pulsos, por ejemplo para
     dosificacion o medicion de precision?

REGLAS DE TRADUCCION TECNICA:
- Si NO sabe el CAUDAL: pregunta volumen del deposito y tiempo de vaciado. Convierte tu internamente a m3/h.
- Si NO sabe la ALTURA ESTATICA: explica el desnivel vertical desde aspiracion hasta descarga.
- Si NO conoce VISCOSIDAD: pregunta a que se parece (agua / aceite / miel) y asigna valores tipicos.
- Si NO sabe DIAMETRO: pregunta si la tuberia ya esta instalada. Si no, asume velocidad 1.5 m/s y propone DN estandar, avisando de la suposicion.
- Densidades tipicas: agua=1000, sosa 30%~1330, acido diluido~1100, aceite~900.
- Viscosidades tipicas: agua=1 cP, sosa 30%~4 cP, aceite~50-200 cP, miel~>1000 cP.
- Para el bloque 6, hazlo con UNA sola pregunta conversacional (p.ej. "¿el fluido lleva
  solidos, es abrasivo, o necesita un caudal muy continuo sin pulsos, como en dosificacion?"),
  no cuatro preguntas separadas. Si el cliente no sabe o no aplica, asume todo en false
  (sin solidos, no abrasivo, no critico en continuidad) y sigue adelante sin insistir.

REGLAS DE FORMATO:
1. UNA sola pregunta a la vez.
2. Tono profesional, servicial y educativo.
3. NUNCA inventes condiciones de la instalacion.
4. Cuando tengas TODA la informacion confirmada, responde UNICAMENTE con JSON estricto (sin texto extra):
{"flow_m3h": float, "diameter_mm": float, "length_m": float, "static_head_m": float, "density_kg_m3": float, "viscosity_cp": float, "fluid_name": "string", "has_solids": bool, "is_abrasive": bool, "is_shear_sensitive": bool, "requires_continuous_flow": bool}
"""


class InterviewAgent:
    SYSTEM_PROMPT = SYSTEM_PROMPT

    @classmethod
    def process_message(cls, user_message: str, chat_history: Optional[List[dict]] = None) -> dict:
        history = chat_history or []

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

        return cls._parse_reply(reply)

    @classmethod
    def _parse_reply(cls, reply: str) -> dict:
        json_match = re.search(r"\{.*\}", reply, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                fluid = data.pop("fluid_name", "Agua")
                req = HydraulicCalculationRequest(**data, fluid_name=fluid)
                payload = req.model_dump()
                return {
                    "status": "complete",
                    "data": payload,
                    "message": "Datos completos. Listo para calculo hidraulico.",
                }
            except Exception as e:
                return {"status": "error", "message": f"Error parseando datos: {e}"}
        return {"status": "incomplete", "message": reply}

    @classmethod
    def _rule_based(cls, user_message: str, history: List[dict]) -> dict:
        """Fallback sin OpenAI: entrevista guiada por contador de turnos."""
        n = len([h for h in history if h.get("role") == "user"])
        msg = user_message.lower()

        if "{" in user_message:
            return cls._parse_reply(user_message)

        questions = [
            "Hola, soy EPi. Para dimensionar su bomba, empecemos por el caudal. ¿Que caudal necesita en m3/h? (Si no lo sabe: digame el volumen del deposito y en cuanto tiempo debe vaciarlo.)",
            "¿Cual es la altura estatica (desnivel vertical en metros) entre la aspiracion y el punto de descarga?",
            "¿Que longitud total tiene la tuberia (metros)?",
            "¿Cual es el diametro interior de la tuberia (mm)? Si no esta definida, puedo proponer un DN con velocidad ~1.5 m/s.",
            "¿Que fluido bombea? (ej: agua, sosa caustica 30%, aceite...). Indique nombre y, si puede, densidad y viscosidad.",
            "Una ultima pregunta para elegir bien la TECNOLOGIA de bomba: ¿el fluido lleva "
            "solidos en suspension, es abrasivo (lodos, arenas...), es delicado (no debe "
            "agitarse mecanicamente), o necesita un caudal muy continuo sin pulsos (por "
            "ejemplo para dosificacion de precision)? Si nada de esto aplica, dígamelo y "
            "seguimos.",
        ]

        # bloque 6 (naturaleza del proceso), detectado por palabras clave sobre el
        # ultimo mensaje del cliente — solo se evalua en el turno de esa pregunta.
        process_flags = {
            "has_solids": False, "is_abrasive": False,
            "is_shear_sensitive": False, "requires_continuous_flow": False,
        }
        if n == 6:
            if any(k in msg for k in ("solido", "solidos", "particula", "fibra")):
                process_flags["has_solids"] = True
            if any(k in msg for k in ("abrasiv", "lodo", "arena", "fango")):
                process_flags["is_abrasive"] = True
            if any(k in msg for k in ("delicad", "fragil", "cizalla", "no debe agitar", "sensible")):
                process_flags["is_shear_sensitive"] = True
            if any(k in msg for k in ("continuo", "sin pulso", "dosifica", "precision", "medicion")):
                process_flags["requires_continuous_flow"] = True

        if n >= 6:
            data = {
                "flow_m3h": 15.0,
                "diameter_mm": 50.0,
                "length_m": 25.0,
                "static_head_m": 8.0,
                "density_kg_m3": 1000.0,
                "viscosity_cp": 1.0,
                "fluid_name": "Agua",
                **process_flags,
            }
            if "sosa" in msg:
                data.update(density_kg_m3=1330.0, viscosity_cp=4.0, fluid_name="Sosa Caustica 30%")
            return {
                "status": "complete",
                "data": data,
                "message": "Datos estimados (modo sin LLM). Revise antes de confirmar el calculo.",
            }

        return {"status": "incomplete", "message": questions[min(n, len(questions) - 1)]}
