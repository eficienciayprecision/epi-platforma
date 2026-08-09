"""
ChemicalCompatibilityAdvisor — Compatibilidad quimica fluido/material (V8)
============================================================================
EPi ya sabe elegir la TECNOLOGIA de bomba correcta (pump_technology.py).
Este modulo añade la segunda comprobacion de seguridad: que el fluido a
bombear no ataque quimicamente el material que va a tocar (cuerpo mojado
y elastomero/junta de la bomba elegida).

Es deliberadamente conservador: si no hay dato de material de la bomba,
o el fluido no esta en la base de conocimiento, devuelve `compatible=None`
("no se puede descartar ni confirmar, verificar a mano") en vez de asumir
que todo va bien. Un falso "compatible" aqui podria acabar en una bomba
rota o una fuga de producto peligroso en planta; un `None` que obliga a
revisar a mano es un coste mucho menor que un incidente real.

Base de conocimiento de compatibilidad (`_FLUID_DB`): no es exhaustiva.
Cubre los fluidos industriales mas habituales en instalaciones de bombeo
(agua, sosa, acidos comunes, hipoclorito, disolventes, aceites, agua de
mar). Para cualquier fluido fuera de esta lista, o para materiales fuera
del vocabulario que usa nuestra base de datos, el resultado es `None`.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

from app.schemas.epi_schemas import ChemicalCompatibilityResult


def _norm(text: str) -> str:
    text = text.lower().strip()
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return text


# Cada entrada: palabras clave que identifican el fluido -> materiales de
# CUERPO y de ELASTOMERO que NO deben usarse, con el motivo.
_FLUID_DB: List[dict] = [
    {
        "keywords": ["agua", "water"],
        "label": "Agua",
        "bad_body": {},
        "bad_elastomer": {},
    },
    {
        "keywords": ["sosa", "hidroxido de sodio", "naoh", "soda caustica"],
        "label": "Sosa cáustica / hidróxido de sodio",
        "bad_body": {
            "Aluminio": "El aluminio se corroe rápidamente con sosa cáustica (reacción violenta a alta concentración).",
        },
        "bad_elastomer": {},
    },
    {
        "keywords": ["acido clorhidrico", "hcl", "salfuman"],
        "label": "Ácido clorhídrico",
        "bad_body": {
            "Acero inoxidable 304": "El ácido clorhídrico ataca el acero inoxidable (picadura por cloruros), incluso el 316.",
            "Acero inoxidable 316": "El ácido clorhídrico ataca también el 316 a concentraciones/temperaturas altas; valorar PVDF o polipropileno.",
            "Fundición": "El hierro fundido se disuelve en ácido clorhídrico.",
            "Acero al carbono": "El acero al carbono se corroe muy rápido en ácido clorhídrico.",
            "Aluminio": "El aluminio reacciona con el ácido clorhídrico liberando hidrógeno.",
        },
        "bad_elastomer": {
            "EPDM": "El EPDM no resiste bien los ácidos minerales fuertes como el clorhídrico.",
        },
    },
    {
        "keywords": ["acido sulfurico"],
        "label": "Ácido sulfúrico",
        "bad_body": {
            "Fundición": "El hierro fundido se corroe con ácido sulfúrico.",
            "Acero al carbono": "El acero al carbono se corroe con ácido sulfúrico.",
            "Aluminio": "El aluminio no resiste el ácido sulfúrico.",
        },
        "bad_elastomer": {
            "Nitrilo (NBR/Buna-N)": "El nitrilo se degrada con ácido sulfúrico concentrado.",
        },
    },
    {
        "keywords": ["hipoclorito", "lejia", "cloro"],
        "label": "Hipoclorito sódico / lejía",
        "bad_body": {
            "Acero inoxidable 304": "El hipoclorito (cloro activo) pica el acero inoxidable 304; usar 316, PVDF o polipropileno.",
            "Fundición": "El hierro fundido se corroe con hipoclorito.",
            "Aluminio": "El aluminio no resiste el hipoclorito sódico.",
        },
        "bad_elastomer": {
            "Nitrilo (NBR/Buna-N)": "El nitrilo se degrada por oxidación con hipoclorito; mejor EPDM o Viton.",
            "Caucho natural (NR)": "El caucho natural se degrada con hipoclorito (agente oxidante).",
        },
    },
    {
        "keywords": ["acetona", "mek", "metil etil cetona", "disolvente", "tolueno", "xileno", "cetona"],
        "label": "Disolventes / cetonas / aromáticos",
        "bad_body": {
            "Polipropileno": "Los disolventes fuertes atacan/hinchan el polipropileno; valorar PVDF, acero inoxidable o aluminio.",
        },
        "bad_elastomer": {
            "EPDM": "El EPDM se hincha y degrada con disolventes/cetonas.",
            "Nitrilo (NBR/Buna-N)": "El nitrilo se hincha con cetonas y algunos disolventes.",
            "Caucho natural (NR)": "El caucho natural no resiste disolventes orgánicos.",
        },
    },
    {
        "keywords": ["aceite", "hidrocarburo", "gasoil", "diesel", "gasolina", "mineral oil"],
        "label": "Aceites minerales / hidrocarburos",
        "bad_body": {},
        "bad_elastomer": {
            "EPDM": "El EPDM se hincha y degrada en contacto con aceites minerales/hidrocarburos.",
            "Caucho natural (NR)": "El caucho natural no resiste bien los aceites minerales.",
        },
    },
    {
        "keywords": ["agua de mar", "agua salada", "salmuera"],
        "label": "Agua de mar / salmuera",
        "bad_body": {
            "Acero al carbono": "El acero al carbono se corroe rápido con agua salada.",
            "Fundición": "La fundición se corroe con agua salada; usar 316, PVDF o polipropileno.",
            "Aluminio": "El aluminio pica con el agua de mar.",
        },
        "bad_elastomer": {},
    },
]


class ChemicalCompatibilityAdvisor:
    @classmethod
    def bad_materials_for(cls, fluid_name: str) -> tuple[set, set]:
        """Devuelve (materiales_de_cuerpo_a_evitar, materiales_de_elastomero_a_evitar)
        para un fluido, o (set(), set()) si el fluido no esta en la base de
        conocimiento. Se usa ANTES de elegir bomba, para descartar candidatas
        quimicamente incompatibles cuando hay alternativa dentro del mismo
        caudal/altura/perfil/tecnologia."""
        fluid_norm = _norm(fluid_name or "")
        entry = None
        best_len = 0
        for candidate in _FLUID_DB:
            for kw in candidate["keywords"]:
                kw_norm = _norm(kw)
                if kw_norm in fluid_norm and len(kw_norm) > best_len:
                    entry = candidate
                    best_len = len(kw_norm)
        if entry:
            return set(entry["bad_body"].keys()), set(entry["bad_elastomer"].keys())
        return set(), set()

    @classmethod
    def check(
        cls,
        fluid_name: str,
        body_material: Optional[str],
        elastomer_material: Optional[str],
    ) -> ChemicalCompatibilityResult:
        fluid_norm = _norm(fluid_name or "")
        entry = None
        best_len = 0
        for candidate in _FLUID_DB:
            for kw in candidate["keywords"]:
                kw_norm = _norm(kw)
                if kw_norm in fluid_norm and len(kw_norm) > best_len:
                    entry = candidate
                    best_len = len(kw_norm)

        warnings: List[str] = []

        if entry is None:
            warnings.append(
                f"'{fluid_name}' no está en la base de compatibilidad química de EPi "
                f"(cubre agua, sosa, ácidos comunes, hipoclorito, disolventes, aceites y "
                f"agua de mar). No se puede confirmar ni descartar la compatibilidad: "
                f"verificar con la ficha del fabricante antes de ofertar."
            )
            return ChemicalCompatibilityResult(
                fluid_name=fluid_name, body_material=body_material,
                elastomer_material=elastomer_material, compatible=None, warnings=warnings,
            )

        if not body_material and not elastomer_material:
            warnings.append(
                f"No hay dato de material para esta bomba en la base de datos de EPi. "
                f"Con {entry['label']}, verificar manualmente el material de cuerpo y "
                f"junta/elastómero antes de ofertar."
            )
            return ChemicalCompatibilityResult(
                fluid_name=fluid_name, body_material=body_material,
                elastomer_material=elastomer_material, compatible=None, warnings=warnings,
            )

        incompatible = False
        if body_material and body_material in entry["bad_body"]:
            incompatible = True
            warnings.append(f"Cuerpo ({body_material}): {entry['bad_body'][body_material]}")
        if elastomer_material and elastomer_material in entry["bad_elastomer"]:
            incompatible = True
            warnings.append(f"Elastómero ({elastomer_material}): {entry['bad_elastomer'][elastomer_material]}")

        if incompatible:
            return ChemicalCompatibilityResult(
                fluid_name=fluid_name, body_material=body_material,
                elastomer_material=elastomer_material, compatible=False, warnings=warnings,
            )

        # Sin incompatibilidad detectada, pero solo lo decimos "compatible=True"
        # si conocemos AMBOS materiales; si falta uno, queda como duda razonable.
        if body_material and elastomer_material:
            return ChemicalCompatibilityResult(
                fluid_name=fluid_name, body_material=body_material,
                elastomer_material=elastomer_material, compatible=True, warnings=[],
            )

        warnings.append(
            f"Solo se conoce parte del material de esta bomba "
            f"(cuerpo={body_material or '?'}, elastómero={elastomer_material or '?'}). "
            f"No hay incompatibilidad conocida con {entry['label']}, pero verificar el "
            f"material que falta antes de confirmar."
        )
        return ChemicalCompatibilityResult(
            fluid_name=fluid_name, body_material=body_material,
            elastomer_material=elastomer_material, compatible=None, warnings=warnings,
        )
