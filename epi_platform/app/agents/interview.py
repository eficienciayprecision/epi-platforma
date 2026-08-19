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
Tu objetivo es obtener 7 bloques de variables clave de un cliente para dimensionar una bomba
industrial, adaptandote a su nivel tecnico.

BLOQUE 0 (SIEMPRE PRIMERO, ANTES DE CUALQUIER OTRA PREGUNTA):
Pregunta si quiere mejorar/diseñar TODA la instalación (tuberías, válvulas, accesorios,
mano de obra) o si SOLO necesita cotizar la bomba en sí (scope). Formula una unica
pregunta clara, por ejemplo: "Antes de nada: ¿quiere que le ayude a mejorar toda la
instalación, o solo necesita cotizar/cambiar la bomba?". Interpreta la respuesta como
"instalacion" o "bomba" (si es ambigua, pregunta de nuevo con esas dos opciones explicitas).
Este bloque NO cambia el resto de preguntas: en ambos casos necesitas los mismos datos
hidraulicos (bloques 1-6) para poder dimensionar/seleccionar la bomba correctamente.

LOS 6 BLOQUES HIDRAULICOS (despues del bloque 0):
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
4. Cuando tengas TODA la informacion confirmada (incluido el bloque 0), responde UNICAMENTE
   con JSON estricto (sin texto extra), incluyendo "scope" con el valor "instalacion" o "bomba":
{"scope": "instalacion|bomba", "flow_m3h": float, "diameter_mm": float, "length_m": float, "static_head_m": float, "density_kg_m3": float, "viscosity_cp": float, "fluid_name": "string", "has_solids": bool, "is_abrasive": bool, "is_shear_sensitive": bool, "requires_continuous_flow": bool}
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

        model = os.getenv("EPI_LLM_MODEL", "gpt-4o-mini")
        kwargs = {"model": model, "messages": messages}
        if model.startswith("gpt-5"):
            # Modelos de razonamiento (GPT-5.x): no admiten temperature libre
            # (algunos la ignoran, otros dan error). Se usa reasoning_effort;
            # "low" prioriza respuestas rapidas, adecuado para una entrevista
            # conversacional turno a turno.
            kwargs["reasoning_effort"] = os.getenv("EPI_LLM_REASONING_EFFORT", "low")
        else:
            kwargs["temperature"] = 0.2

        try:
            response = _client.chat.completions.create(**kwargs)
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
                # "scope" no forma parte de HydraulicCalculationRequest (es
                # hidraulicamente irrelevante) — se extrae aparte y se
                # reincorpora al payload plano que ve el frontend, para que
                # pueda decidir si llamar a /solution/oneshot (instalacion
                # completa) o a /solution/pump-only (solo la bomba).
                scope = data.pop("scope", "instalacion")
                if scope not in ("instalacion", "bomba"):
                    scope = "instalacion"
                req = HydraulicCalculationRequest(**data, fluid_name=fluid)
                payload = req.model_dump()
                payload["scope"] = scope
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
            m = re.search(r"(\d+\.?\d*)\s*(l/min|l/m\b|lpm|lts?/min|litros?\s*/?\s*min(?:uto)?s?|litros?\s+por\s+minuto)", up)
            if m:
                extracted["flow_m3h"] = round(float(m.group(1)) * 60 / 1000, 3)
            else:
                m = re.search(r"(\d+\.?\d*)\s*(l/h|lts?/h|litros?\s*/?\s*h(?:ora)?s?|litros?\s+por\s+hora)", up)
                if m:
                    extracted["flow_m3h"] = round(float(m.group(1)) / 1000, 4)
                else:
                    m = re.search(r"(\d+\.?\d*)\s*m3/s", up)
                    if m:
                        extracted["flow_m3h"] = round(float(m.group(1)) * 3600, 3)

        head_kw = r"altura\s*est[aá]tica|altura|desnivel"
        # se prueba primero el orden "3 metros de altura" (mas natural cuando
        # van varias frases seguidas, p.ej. "3 metros de altura 8 metros de
        # tuberia" — si se probara el otro orden primero, "altura" podria
        # engancharse por error con el "8" de la frase siguiente).
        m = re.search(rf"(\d+\.?\d*)\s*m(?:etros)?\s+de\s+(?:{head_kw})\b", up)
        if not m:
            m = re.search(rf"(?:{head_kw})(?:\s+de)?\s+(\d+\.?\d*)\s*m(?:etros)?\b", up)
        if m:
            extracted["static_head_m"] = float(m.group(1))

        len_kw = r"longitud|tuber[ií]a|tubo"
        m = re.search(rf"(\d+\.?\d*)\s*m(?:etros)?\s+de\s+(?:{len_kw})\b", up)
        if not m:
            m = re.search(rf"(?:{len_kw})(?:\s+de)?\s+(\d+\.?\d*)\s*m(?:etros)?\b", up)
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

        # NUEVO — ampliado el diccionario de fluidos reconocidos (densidad y
        # viscosidad aproximadas, valores tipicos de referencia) y marcado
        # explicitamente cuando el fluido mencionado NO se reconoce, para no
        # asumir agua en silencio sin que quede constancia de la suposicion.
        fluid_db = [
            (("sosa",), "Sosa Cáustica 30%", 1330.0, 4.0),
            (("hipoclorito", "lejia", "lejía"), "Hipoclorito sódico", 1150.0, 2.0),
            (("acido sulfurico", "ácido sulfúrico"), "Ácido sulfúrico diluido", 1300.0, 3.0),
            (("acido clorhidrico", "ácido clorhídrico", "hcl"), "Ácido clorhídrico diluido", 1150.0, 2.0),
            (("acido", "ácido"), "Ácido diluido", 1100.0, 2.0),
            (("etanol", "alcohol"), "Etanol", 789.0, 1.2),
            (("glicerina", "glicerol"), "Glicerina", 1260.0, 1400.0),
            (("aceite hidraulico", "aceite hidráulico"), "Aceite hidráulico", 870.0, 46.0),
            (("aceite",), "Aceite", 900.0, 100.0),
            (("gasoil", "diesel", "gasóleo"), "Gasóleo", 840.0, 4.0),
            (("leche",), "Leche", 1030.0, 2.0),
            (("mosto", "vino"), "Mosto/Vino", 1010.0, 1.5),
            (("melaza", "miel"), "Melaza/Miel", 1400.0, 2000.0),
            (("salmuera",), "Salmuera", 1200.0, 1.5),
            (("agua de mar",), "Agua de mar", 1025.0, 1.1),
            (("agua",), "Agua", 1000.0, 1.0),
        ]
        matched = False
        for keywords, name, density, viscosity in fluid_db:
            if any(kw in up for kw in keywords):
                extracted.update(fluid_name=name, density_kg_m3=density, viscosity_cp=viscosity)
                matched = True
                break
        if not matched:
            # se guarda el nombre tal cual lo escribio el cliente, pero SIN
            # asumir una densidad — main.py avisa de esto en la oferta en
            # vez de calcular en silencio como si fuera agua
            m_fluid = re.search(r'(?:fluido|producto|liquido)\s*(?:es|:)?\s*([a-záéíóúñ0-9%\s]{3,40})', up)
            if m_fluid:
                candidate = m_fluid.group(1).strip()
                if candidate and candidate not in ("no", "no lo se", "no lo sé"):
                    extracted.update(fluid_name=candidate.title(), fluid_density_unknown=True)

        return extracted

    @classmethod
    def _extract_scope(cls, text: str) -> Optional[str]:
        """NUEVO — interpreta la respuesta a la pregunta inicial (bloque 0):
        ¿mejorar toda la instalación, o solo cotizar la bomba? Devuelve
        "instalacion", "bomba", o None si la respuesta es ambigua/no dice
        nada al respecto (en cuyo caso se sigue preguntando)."""
        up = text.lower()
        has_bomba = bool(re.search(r'\bbomba\b', up))
        has_instal = bool(re.search(r'instalaci[oó]n', up))
        if re.search(r'(solo|solamente|s[oó]lo|[uú]nicamente)[^.]{0,20}\bbomba\b', up):
            return "bomba"
        if has_instal and not has_bomba:
            return "instalacion"
        if has_bomba and not has_instal:
            return "bomba"
        return None

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
        """Fallback sin OpenAI: en cada mensaje intenta extraer por palabras
        clave los datos que el cliente ya haya dado (en cualquier orden,
        aunque los de todos juntos en la primera respuesta), y solo
        pregunta por lo que de verdad falte.

        Ademas de la extraccion por palabra clave (que capta "3 metros de
        altura" venga cuando venga), se empareja cada pregunta ya formulada
        con la respuesta que le siguio: si esa respuesta concreta no se
        capto por palabra clave (p.ej. el cliente contesta solo "8" o "8
        metros" sin repetir "tuberia"), se usa tal cual como respuesta a
        ESA pregunta — evita quedarse repitiendo la misma pregunta para
        siempre. Este emparejamiento es lo que permite que el dato quede
        fijado de forma permanente turno a turno (antes se recalculaba todo
        desde cero en cada mensaje y el dato se "olvidaba" en el turno
        siguiente si no volvia a coincidir por palabra clave)."""
        if "{" in user_message:
            return cls._parse_reply(user_message)

        required_order = ["scope", "flow_m3h", "static_head_m", "length_m", "diameter_mm", "fluid_name"]
        question_for = {
            "scope": "Antes de nada: ¿quiere que le ayude a mejorar TODA la instalación (tuberías, "
                     "válvulas, accesorios), o solo necesita cotizar/cambiar la BOMBA? Responda "
                     "\"instalación\" o \"bomba\".",
            "flow_m3h": "¿Que caudal necesita en m3/h? (Si no lo sabe: digame el volumen del deposito y en cuanto tiempo debe vaciarlo.)",
            "static_head_m": "¿Cual es la altura estatica (desnivel vertical en metros) entre la aspiracion y el punto de descarga?",
            "length_m": "¿Que longitud total tiene la tuberia (metros)?",
            "diameter_mm": "¿Cual es el diametro interior de la tuberia (mm)? Si no esta definida, puedo proponer un DN con velocidad ~1.5 m/s.",
            "fluid_name": "¿Que fluido bombea? (ej: agua, sosa caustica 30%, aceite...). Indique nombre y, si puede, densidad y viscosidad.",
        }

        # El frontend ya incluye el mensaje actual como ultimo elemento de
        # `history` (lo añade antes de llamar al endpoint) — no hay que
        # volver a añadirlo aparte.
        all_user_texts = [h.get("content", "") for h in history if h.get("role") == "user"]
        if not all_user_texts:
            all_user_texts = [user_message]

        collected: dict = {}
        for t in all_user_texts:
            for k, v in cls._extract_fields(t).items():
                collected.setdefault(k, v)
            if "scope" not in collected:
                scope_guess = cls._extract_scope(t)
                if scope_guess:
                    collected["scope"] = scope_guess

        # Emparejar cada pregunta de campo ya formulada con la respuesta que
        # le siguio inmediatamente, y usarla tal cual si la extraccion por
        # palabra clave no la capto.
        diameter_auto_selected = False
        last_q = None
        for h in history:
            role = h.get("role")
            if role == "assistant":
                last_q = h.get("content", "")
            elif role == "user" and last_q is not None:
                field = next((f for f, q in question_for.items() if q == last_q), None)
                if field and field not in collected:
                    answer = h.get("content", "")
                    if field == "scope":
                        # Respuesta directa a la pregunta inicial: si no se
                        # entiende con claridad, se asume "instalacion" (el
                        # comportamiento de siempre) en vez de re-preguntar
                        # indefinidamente.
                        collected["scope"] = cls._extract_scope(answer) or "instalacion"
                    elif field == "fluid_name":
                        txt = answer.strip()
                        if txt and not re.fullmatch(r"[\d.,\s]+", txt):
                            collected["fluid_name"] = txt
                    elif field == "diameter_mm" and re.search(
                        r'\bno\s+(lo\s+)?s[eé]\b|\bno\s+est[aá]\s+(definid|instalad)|\bnueva\b|\ba\s+definir\b|\bno\s+lo\s+tengo\b',
                        answer.lower(),
                    ):
                        # NUEVO — antes esto se quedaba bloqueado para
                        # siempre si el cliente no sabia el diametro, pese a
                        # que la pregunta ya prometia proponer uno. Ahora se
                        # calcula de verdad el diametro economico optimo
                        # (mejor relacion tuberia+energia, no solo el mas
                        # barato de comprar) con los datos ya recogidos.
                        if all(k in collected for k in ("flow_m3h", "static_head_m", "length_m")):
                            from app.engine.hydraulics import HydraulicEngine
                            rec = HydraulicEngine.recommend_diameter(
                                flow_m3h=collected["flow_m3h"],
                                length_m=collected["length_m"],
                                static_head_m=collected["static_head_m"],
                                k_accessories=2.5,
                                density_kg_m3=1000.0,  # se corrige mas adelante segun el fluido
                                viscosity_cp=1.0,
                            )
                            collected["diameter_mm"] = rec["recommended"]["diameter_mm"]
                            diameter_auto_selected = True
                    else:
                        m = re.search(r"(\d+\.?\d*)", answer.replace(",", "."))
                        if m:
                            collected[field] = float(m.group(1))
                last_q = None

        process_flags = {
            "has_solids": False, "is_abrasive": False,
            "is_shear_sensitive": False, "requires_continuous_flow": False,
        }
        for t in all_user_texts:
            flags = cls._extract_process_flags(t)
            for k, v in flags.items():
                process_flags[k] = process_flags[k] or v

        missing = [f for f in required_order if f not in collected]

        if missing:
            greeting = "Hola, soy EPi. " if not history else ""
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
            "scope": collected.get("scope", "instalacion"),
            "flow_m3h": collected["flow_m3h"],
            "diameter_mm": collected["diameter_mm"],
            "length_m": collected["length_m"],
            "static_head_m": collected["static_head_m"],
            "density_kg_m3": collected.get("density_kg_m3", 1000.0),
            "viscosity_cp": collected.get("viscosity_cp", 1.0),
            "fluid_name": collected.get("fluid_name", "Agua"),
            "diameter_auto_selected": diameter_auto_selected,
            "fluid_density_unknown": collected.get("fluid_density_unknown", False),
            **process_flags,
        }
        notes = []
        if diameter_auto_selected:
            notes.append(
                "El diámetro de tubería no estaba definido: se ha calculado el DN de mejor "
                "relación calidad-precio (equilibrio entre coste de tubería y coste "
                "energético), no simplemente el más barato de comprar."
            )
        if data["fluid_density_unknown"]:
            notes.append(
                f"No se ha reconocido con confianza la densidad de \"{data['fluid_name']}\" — "
                "se recomienda confirmarla antes de dar la oferta por definitiva, ya que afecta "
                "a la potencia y al caudal real de bombas centrífugas."
            )
        message = "Datos completos (modo sin LLM, leidos por palabras clave de sus mensajes). Revise antes de confirmar el calculo."
        if notes:
            message += " " + " ".join(notes)
        return {
            "status": "complete",
            "data": data,
            "message": message,
        }
