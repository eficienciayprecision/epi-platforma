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
    def _extract_fields(cls, text: str) -> dict:
        """Extrae por palabras clave los datos que el cliente ya haya dado,
        en cualquier orden ('altura de 8 m' o '8 m de altura' valen igual).
        Best-effort: no entiende tan bien como un LLM real, pero evita
        re-preguntar datos que el cliente ya dio y evita usar siempre los
        mismos valores de ejemplo cuando no hay OPENAI_API_KEY configurada."""
        up = text.lower().replace(",", ".")
        extracted: dict = {}

        m = re.search(r"(\d+\.?\d*)\s*(m3/h|m³/h|m3h)", up)
        if m:
            extracted["flow_m3h"] = float(m.group(1))
        else:
            m = re.search(r"(\d+\.?\d*)\s*(l/min|lpm)", up)
            if m:
                extracted["flow_m3h"] = round(float(m.group(1)) * 60 / 1000, 3)
            else:
                m = re.search(r"(\d+\.?\d*)\s*m3/s", up)
                if m:
                    extracted["flow_m3h"] = round(float(m.group(1)) * 3600, 3)

        head_kw = r"altura\s*est[aá]tica|altura|desnivel"
        m = re.search(rf"(?:{head_kw})(?:\s+de)?\s+(\d+\.?\d*)\s*m(?:etros)?\b", up)
        if not m:
            m = re.search(rf"(\d+\.?\d*)\s*m(?:etros)?\s+de\s+(?:{head_kw})\b", up)
        if m:
            extracted["static_head_m"] = float(m.group(1))

        len_kw = r"longitud|tuber[ií]a|tubo"
        m = re.search(rf"(?:{len_kw})(?:\s+de)?\s+(\d+\.?\d*)\s*m(?:etros)?\b", up)
        if not m:
            m = re.search(rf"(\d+\.?\d*)\s*m(?:etros)?\s+de\s+(?:{len_kw})\b", up)
        if m:
            extracted["length_m"] = float(m.group(1))

        m = re.search(r"(\d+\.?\d*)\s*mm\b", up)
        if m:
            extracted["diameter_mm"] = float(m.group(1))
        else:
            m = re.search(r'(\d+\.?\d*)\s*(pulgada|inch|")', up)
            if m:
                extracted["diameter_mm"] = round(float(m.group(1)) * 25.4, 1)
            else:
                m = re.search(r"\bdn\s?(\d+)\b", up)
                if m:
                    extracted["diameter_mm"] = float(m.group(1))

        if "sosa" in up:
            extracted.update(fluid_name="Sosa Caustica 30%", density_kg_m3=1330.0, viscosity_cp=4.0)
        elif "acido" in up:
            extracted.update(fluid_name="Acido diluido", density_kg_m3=1100.0, viscosity_cp=2.0)
        elif "aceite" in up:
            extracted.update(fluid_name="Aceite", density_kg_m3=900.0, viscosity_cp=100.0)
        elif "miel" in up:
            extracted.update(fluid_name="Miel", density_kg_m3=1400.0, viscosity_cp=2000.0)
        elif "agua" in up:
            extracted.update(fluid_name="Agua", density_kg_m3=1000.0, viscosity_cp=1.0)

        return extracted

    @classmethod
    def _extract_process_flags(cls, text: str) -> dict:
        up = text.lower()
        # negacion generica de todo el bloque ("no", "no lleva nada especial"...)
        if re.search(r'\bno\b[^.]{0,25}\b(nada|especial|aplica|de eso)\b', up) or up.strip() in ("no", "no.", "ninguno", "ninguna", "no aplica", "nada"):
            return {"has_solids": False, "is_abrasive": False, "is_shear_sensitive": False, "requires_continuous_flow": False}

        def _positive(keywords: tuple) -> bool:
            for kw in keywords:
                for m in re.finditer(kw, up):
                    # si hay una negacion ("no", "sin") justo antes de la palabra clave, no cuenta
                    window_before = up[max(0, m.start() - 15):m.start()]
                    if re.search(r'\b(no|sin)\b\s*\w*\s*$', window_before):
                        continue
                    return True
            return False

        return {
            "has_solids": _positive(("solido", "solidos", "particula", "fibra")),
            "is_abrasive": _positive(("abrasiv", "lodo", "arena", "fango")),
            "is_shear_sensitive": _positive(("delicad", "fragil", "cizalla", "sensible")),
            "requires_continuous_flow": _positive(("continuo", "sin pulso", "dosifica", "precision", "medicion")),
        }

    @classmethod
    def _rule_based(cls, user_message: str, history: List[dict]) -> dict:
        """Fallback sin OpenAI: ya NO se basa solo en contar turnos — en cada
        mensaje intenta extraer por palabras clave los datos que el cliente
        ya haya dado (en cualquier orden, aunque los de todos juntos en la
        primera respuesta), y solo pregunta por lo que de verdad falte."""
        if "{" in user_message:
            return cls._parse_reply(user_message)

        all_user_texts = [h.get("content", "") for h in history if h.get("role") == "user"] + [user_message]

        collected: dict = {}
        for t in all_user_texts:
            for k, v in cls._extract_fields(t).items():
                collected.setdefault(k, v)

        process_flags = {
            "has_solids": False, "is_abrasive": False,
            "is_shear_sensitive": False, "requires_continuous_flow": False,
        }
        for t in all_user_texts:
            flags = cls._extract_process_flags(t)
            for k, v in flags.items():
                process_flags[k] = process_flags[k] or v

        required_order = ["flow_m3h", "static_head_m", "length_m", "diameter_mm", "fluid_name"]
        question_for = {
            "flow_m3h": "¿Que caudal necesita en m3/h? (Si no lo sabe: digame el volumen del deposito y en cuanto tiempo debe vaciarlo.)",
            "static_head_m": "¿Cual es la altura estatica (desnivel vertical en metros) entre la aspiracion y el punto de descarga?",
            "length_m": "¿Que longitud total tiene la tuberia (metros)?",
            "diameter_mm": "¿Cual es el diametro interior de la tuberia (mm)? Si no esta definida, puedo proponer un DN con velocidad ~1.5 m/s.",
            "fluid_name": "¿Que fluido bombea? (ej: agua, sosa caustica 30%, aceite...). Indique nombre y, si puede, densidad y viscosidad.",
        }
        missing = [f for f in required_order if f not in collected]

        if missing:
            greeting = "Hola, soy EPi. " if not all_user_texts[:-1] else ""
            return {"status": "incomplete", "message": greeting + question_for[missing[0]]}

        # Los 5 datos hidraulicos ya estan. Falta el bloque de proceso — se
        # pregunta una unica vez, detectando si ya se pregunto antes por si
        # aparece en el historial de mensajes del asistente.
        block6_question = (
            "Una ultima pregunta para elegir bien la TECNOLOGIA de bomba: ¿el fluido lleva "
            "solidos en suspension, es abrasivo (lodos, arenas...), es delicado (no debe "
            "agitarse mecanicamente), o necesita un caudal muy continuo sin pulsos (por "
            "ejemplo para dosificacion de precision)? Si nada de esto aplica, dígamelo y "
            "seguimos."
        )
        already_asked_block6 = any(
            "TECNOLOGIA de bomba" in h.get("content", "")
            for h in history if h.get("role") == "assistant"
        )
        if not already_asked_block6:
            return {"status": "incomplete", "message": block6_question}

        data = {
            "flow_m3h": collected["flow_m3h"],
            "diameter_mm": collected["diameter_mm"],
            "length_m": collected["length_m"],
            "static_head_m": collected["static_head_m"],
            "density_kg_m3": collected.get("density_kg_m3", 1000.0),
            "viscosity_cp": collected.get("viscosity_cp", 1.0),
            "fluid_name": collected.get("fluid_name", "Agua"),
            **process_flags,
        }
        return {
            "status": "complete",
            "data": data,
            "message": "Datos completos (modo sin LLM, leidos por palabras clave de sus mensajes). Revise antes de confirmar el calculo.",
        }
