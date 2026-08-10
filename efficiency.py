"""Agente de asesoramiento de eficiencia energetica de planta.

A diferencia del agente de entrevista (interview.py), que recopila variables
estructuradas para dimensionar UNA bomba nueva, este agente recibe una
descripcion libre de una instalacion YA EXISTENTE y devuelve recomendaciones
de mejora de eficiencia: sustitucion o revision de bombas poco eficientes,
reduccion de perdidas de carga (menos codos/valvulas estranguladas, tramos
mas cortos o de mayor diametro) y, cuando hay datos suficientes, una
estimacion de ahorro apoyandose en EnergyOptimizer.
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
Eres EPi, un ingeniero experto en eficiencia energetica de instalaciones de bombeo industrial,
en 'Eficiencia y Precision Industrial S.L.'.

El cliente te va a describir, en texto libre y con sus propias palabras, una instalacion de
bombeo o dosificacion YA EXISTENTE (no una instalacion nueva a dimensionar). Tu trabajo es
identificar oportunidades de mejora de eficiencia y de reduccion de consumo energetico,
razonando SIEMPRE sobre estos dos frentes:

1. EFICIENCIA DE CADA BOMBA: si el cliente menciona la marca/modelo, la antiguedad, si trabaja
   con valvula de estrangulamiento en vez de variador de frecuencia (VFD), o si el punto de
   trabajo parece alejado del punto de mejor rendimiento (BEP) de la bomba, señalalo como
   oportunidad de mejora.
2. REDUCCION DE PERDIDAS DE CARGA: cada perdida de carga (por friccion en tuberia larga o de
   diametro insuficiente, por codos y accesorios innecesarios, por valvulas parcialmente
   cerradas) obliga a la bomba a trabajar mas de lo necesario, lo que se traduce DIRECTAMENTE
   en mayor consumo electrico. Identifica en la descripcion del cliente cualquier elemento que
   pueda estar generando perdidas de carga evitables (codos de radio corto, tuberia
   sobredimensionada o infradimensionada, valvulas de globo muy estranguladas, tramos
   innecesariamente largos) y explica, en terminos sencillos, por que reducirlas ahorra energia.

FORMATO DE RESPUESTA:
- Si la descripcion del cliente es muy breve o generica, haz UNA pregunta de aclaracion a la vez
  (por ejemplo: cuantas bombas hay, que fluido mueven, si usan variador de frecuencia, cuantas
  horas al dia funcionan, si conocen el coste de la energia) antes de dar recomendaciones
  cerradas. No hagas mas de 2-3 preguntas de aclaracion en total; si el cliente no puede
  responder con precision, da recomendaciones generales igualmente.
- Cuando tengas informacion suficiente, responde con una lista clara de recomendaciones
  concretas, priorizadas por impacto, explicando para cada una que perdida de carga o que
  ineficiencia de bomba corrige y por que eso reduce el consumo energetico.
- Tono profesional y didactico. NUNCA inventes datos numericos que el cliente no ha dado;
  si haces una estimacion de ahorro, indica claramente que es orientativa.
"""


class EfficiencyAdvisorAgent:
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
                temperature=0.3,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            return {"status": "error", "message": f"Error LLM: {e}"}

        return {"status": "advice", "message": reply}

    @classmethod
    def _rule_based(cls, user_message: str, history: List[dict]) -> dict:
        """Fallback sin OpenAI: heuristica por palabras clave sobre la ultima descripcion."""
        n = len([h for h in history if h.get("role") == "user"])
        msg = user_message.lower()

        # Nota: `history` llega desde el frontend ya incluyendo el mensaje actual
        # del usuario (mismo convenio que interview.py), por eso el primer envio
        # real del cliente tiene n == 1, no n == 0.
        # Si es el primer mensaje y es muy corto, pide mas contexto (maximo 1 vez).
        if n == 1 and len(user_message.strip()) < 40:
            return {
                "status": "incomplete",
                "message": (
                    "Cuénteme un poco más sobre su planta para poder orientarle: ¿cuántas "
                    "bombas tiene, qué fluido mueven, cuántas horas al día funcionan, y si "
                    "regulan el caudal con una válvula o con un variador de frecuencia (VFD)?"
                ),
            }

        tips: List[str] = []

        if "estrangul" in msg or ("valvula" in msg and "cerrada" in msg) or "válvula" in msg:
            tips.append(
                "Si regula el caudal cerrando parcialmente una válvula, esa válvula genera una "
                "pérdida de carga artificial que la bomba tiene que compensar trabajando más de "
                "lo necesario. Sustituir la regulación por válvula por un variador de frecuencia "
                "(VFD) suele reducir el consumo de forma notable en este tipo de instalaciones "
                "(véase el motor de optimización energética de EPi)."
            )
        if "codo" in msg or "codos" in msg:
            tips.append(
                "Los codos de radio corto generan más pérdida de carga que los de radio amplio; "
                "revisar si se pueden eliminar codos innecesarios o sustituirlos por codos de "
                "radio más amplio reduce la altura que debe vencer la bomba, y con ello su "
                "consumo eléctrico."
            )
        if "antigu" in msg or "vieja" in msg or "años" in msg:
            tips.append(
                "Una bomba antigua suele tener un rendimiento notablemente inferior al de un "
                "modelo actual equivalente; conviene verificar su curva de rendimiento actual "
                "frente al punto de trabajo real de la instalación."
            )
        if "tuberia" in msg or "tubería" in msg or "tramo" in msg:
            tips.append(
                "Un tramo de tubería más largo de lo necesario, o de diámetro insuficiente para "
                "el caudal que mueve, incrementa la pérdida de carga por fricción de forma "
                "proporcional a su longitud; acortar el trazado o aumentar el diámetro donde sea "
                "viable reduce directamente el consumo energético."
            )

        if not tips:
            tips.append(
                "Con la información disponible, las dos palancas de eficiencia a revisar son: "
                "(1) si alguna bomba trabaja lejos de su punto de mejor rendimiento o con "
                "regulación por válvula en vez de variador de frecuencia, y (2) si existen "
                "pérdidas de carga evitables en el trazado (codos innecesarios, tramos largos, "
                "válvulas muy estranguladas) — cada pérdida de carga se traduce directamente en "
                "más consumo eléctrico de la bomba."
            )

        message = (
            "Recomendaciones orientativas para mejorar la eficiencia de su planta:\n- "
            + "\n- ".join(tips)
            + "\n\n(Modo sin IA conversacional: recomendaciones basadas en palabras clave. "
              "Con el asistente completo, EPi profundiza con preguntas específicas sobre cada "
              "bomba y calcula una estimación de ahorro energético.)"
        )
        return {"status": "advice", "message": message}
