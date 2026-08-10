"""
PumpTechnologyAdvisor — Motor de razonamiento de tecnologia de bomba (V7)
==========================================================================
Antes de esta version, EPi elegia bomba SOLO por caudal + altura + perfil de
inversion, sin tener en cuenta el proceso (solidos, abrasividad, necesidad
de flujo continuo). Este motor encapsula el criterio de ingenieria de
mecanica de fluidos para decidir que familia(s) de bomba son viables ANTES
de mirar precio, y por que.

Resumen del criterio (ventajas/inconvenientes de cada tecnologia):

- NEUMATICA DE DOBLE MEMBRANA (AODD): la mas barata, pero la de peor
  eficiencia energetica (tipicamente ~15-25%, el motor de aire comprimido
  desperdicia mucha energia en la conversion). Puede bombear solidos en
  suspension y es autocebante y tolerante a marcha en seco. Da un caudal
  muy pulsante (cada carrera de membrana es un pulso), lo que la hace poco
  adecuada cuando se necesita un caudal continuo o dosificacion precisa. No
  necesita electricidad (buena opcion en zonas ATEX sin instalacion
  electrica).

- PERISTALTICA: excelente para lodos y fluidos abrasivos o con solidos en
  suspension, porque el fluido solo toca el interior del tubo/manguera (sin
  sellos ni valvulas en contacto). Buena para fluidos sensibles al
  cizallamiento (no daña el producto). Dan bastante pulsacion (cada
  compresion del rodillo es un pulso), aunque menos brusca que una
  neumatica. Eficiencia media.

- TORNILLO HELICOIDAL (cavidad progresiva): tambien apta para lodos y
  fluidos abrasivos o viscosos, con la ventaja de dar MUCHOS MENOS PULSOS
  que la peristaltica o la neumatica (caudal casi continuo), lo que la hace
  mejor opcion cuando ademas de manejar solidos se necesita precision de
  dosificacion. Eficiencia media-alta. El rotor/estator se desgasta con
  abrasivos, aunque estan diseñadas para ello.

- CENTRIFUGA (mecanica o de acoplamiento magnetico): muy buena eficiencia
  energetica y caudal continuo, ideal para grandes caudales de fluidos
  limpios o poco cargados. NO es buena opcion con solidos en suspension
  significativos ni fluidos muy abrasivos (desgaste de rodete/voluta,
  perdida de rendimiento). La version de acoplamiento magnetico añade
  estanqueidad total (fugas cero), recomendable con fluidos toxicos,
  corrosivos o en zonas ATEX.

- ENGRANAJES: muy buena eficiencia energetica y el caudal MAS CONTINUO de
  todas las tecnologias (ideal para dosificacion/medicion de precision de
  fluidos limpios y viscosos, p.ej. aceites, adhesivos). NO puede usarse
  con solidos en suspension ni fluidos abrasivos: el juego entre engranajes
  es minimo y cualquier particula daña rapidamente el par de engranajes.

El motor devuelve, para cada tecnologia, si es apta o no y por que
(TechnologyRecommendation), y una puntuacion 0-1 que combina aptitud tecnica
+ eficiencia tipica + encaje con el perfil de inversion. `allowed_technologies()`
devuelve solo las aptas, en el orden en que deberian probarse al buscar bomba
en catalogo.
"""
from __future__ import annotations

from typing import List

from app.schemas.epi_schemas import (
    HydraulicCalculationRequest,
    InvestmentProfile,
    PumpTechnology,
    TechnologyRecommendation,
)

# Eficiencia tipica de cada tecnologia (para puntuar, no es la de una bomba concreta)
_TYPICAL_EFFICIENCY = {
    PumpTechnology.NEUMATICA_DOBLE_MEMBRANA: 0.20,
    PumpTechnology.PERISTALTICA: 0.55,
    PumpTechnology.TORNILLO_HELICOIDAL: 0.60,
    PumpTechnology.CENTRIFUGA_MECANICO: 0.70,
    PumpTechnology.CENTRIFUGA_MAGNETICO: 0.68,
    PumpTechnology.ENGRANAJES: 0.70,
    PumpTechnology.PISTON_NEUMATICO: 0.35,
}

# Coste relativo tipico (para puntuar el encaje con el perfil BARATA/PREMIUM)
_RELATIVE_COST = {
    PumpTechnology.NEUMATICA_DOBLE_MEMBRANA: 1,  # mas barata
    PumpTechnology.PERISTALTICA: 3,
    PumpTechnology.TORNILLO_HELICOIDAL: 3,
    PumpTechnology.CENTRIFUGA_MECANICO: 2,
    PumpTechnology.ENGRANAJES: 3,
    PumpTechnology.CENTRIFUGA_MAGNETICO: 4,  # mas cara (estanqueidad total)
    PumpTechnology.PISTON_NEUMATICO: 2,
}


class PumpTechnologyAdvisor:
    @classmethod
    def evaluate(
        cls,
        req: HydraulicCalculationRequest,
        profile: InvestmentProfile = InvestmentProfile.CALIDAD_PRECIO,
    ) -> List[TechnologyRecommendation]:
        """Evalua las 6 tecnologias frente al proceso descrito. Devuelve la
        lista completa (aptas y no aptas) ordenada de mejor a peor puntuacion,
        para poder explicar tanto la eleccion como el descarte."""

        results: List[TechnologyRecommendation] = []
        for tech in PumpTechnology:
            reasons: List[str] = []
            warnings: List[str] = []
            suitable = True

            # --- Reglas duras (incompatibilidad fisica, no de coste) ---
            if req.has_solids or req.is_abrasive:
                if tech in (PumpTechnology.ENGRANAJES,):
                    suitable = False
                    warnings.append(
                        "Las bombas de engranajes no admiten solidos en suspension ni "
                        "fluidos abrasivos: el juego minimo entre engranajes se daña "
                        "rapidamente con cualquier particula."
                    )
                if tech in (PumpTechnology.CENTRIFUGA_MECANICO, PumpTechnology.CENTRIFUGA_MAGNETICO) and req.is_abrasive:
                    suitable = False
                    warnings.append(
                        "Un fluido abrasivo desgasta rapidamente el rodete y la voluta "
                        "de una bomba centrifuga, reduciendo su vida util y rendimiento."
                    )
                elif tech in (PumpTechnology.CENTRIFUGA_MECANICO, PumpTechnology.CENTRIFUGA_MAGNETICO) and req.has_solids:
                    warnings.append(
                        "Con solidos en suspension, una centrifuga estandar puede "
                        "obstruirse o perder rendimiento; solo recomendable si son "
                        "solidos finos y en baja concentracion (valorar version vortex)."
                    )

            if req.is_shear_sensitive and tech in (
                PumpTechnology.CENTRIFUGA_MECANICO, PumpTechnology.CENTRIFUGA_MAGNETICO,
                PumpTechnology.ENGRANAJES, PumpTechnology.TORNILLO_HELICOIDAL,
            ):
                warnings.append(
                    "Estas tecnologias pueden dañar por cizallamiento un fluido "
                    "delicado; la peristaltica es mas suave con el producto."
                )
                shear_penalty = 0.28
            else:
                shear_penalty = 0.0

            # --- Ventajas / criterio positivo ---
            if tech == PumpTechnology.NEUMATICA_DOBLE_MEMBRANA:
                reasons.append("La opcion mas economica de compra.")
                if req.has_solids:
                    reasons.append("Puede bombear solidos en suspension sin problema.")
                warnings.append(
                    "Peor eficiencia energetica de todas las tecnologias (consumo de "
                    "aire comprimido elevado) y caudal muy pulsante."
                )
                if req.requires_continuous_flow:
                    suitable = False
                    warnings.append(
                        "No es apta si se necesita un caudal continuo o dosificacion "
                        "de precision: cada carrera de membrana genera un pulso."
                    )

            elif tech == PumpTechnology.PERISTALTICA:
                if req.has_solids or req.is_abrasive:
                    reasons.append("Muy adecuada para lodos y fluidos abrasivos o con solidos.")
                if req.is_shear_sensitive:
                    reasons.append("No daña el fluido: el producto solo toca el interior del tubo.")
                warnings.append("Da bastante pulsacion (aunque menos brusca que la neumatica).")
                if req.requires_continuous_flow and (req.has_solids or req.is_abrasive):
                    warnings.append(
                        "Si el caudal continuo es critico Y hay solidos/abrasion, valorar "
                        "mejor tornillo helicoidal (da menos pulsos)."
                    )

            elif tech == PumpTechnology.TORNILLO_HELICOIDAL:
                if req.has_solids or req.is_abrasive:
                    reasons.append("Adecuada para lodos y fluidos abrasivos o viscosos.")
                if req.requires_continuous_flow:
                    reasons.append(
                        "Da un caudal casi continuo (muchos menos pulsos que la "
                        "peristaltica o la neumatica): buena opcion si ademas de "
                        "solidos/abrasion se necesita precision de dosificacion."
                    )
                if req.is_abrasive:
                    warnings.append("El rotor/estator se desgasta con el tiempo; prever repuesto.")

            elif tech in (PumpTechnology.CENTRIFUGA_MECANICO, PumpTechnology.CENTRIFUGA_MAGNETICO):
                if not req.has_solids and not req.is_abrasive:
                    reasons.append("Muy buena eficiencia energetica y caudal continuo.")
                if tech == PumpTechnology.CENTRIFUGA_MAGNETICO:
                    reasons.append("Estanqueidad total (fugas cero): recomendable con fluidos toxicos/corrosivos o en zona ATEX.")

            elif tech == PumpTechnology.ENGRANAJES:
                if not req.has_solids and not req.is_abrasive:
                    reasons.append("Muy buena eficiencia energetica.")
                    if req.requires_continuous_flow:
                        reasons.append(
                            "Da el caudal mas continuo de todas las tecnologias: la mejor "
                            "opcion para dosificacion/medicion de precision de fluidos "
                            "limpios y viscosos (aceites, adhesivos...)."
                        )
                if req.viscosity_cp > 50:
                    reasons.append("Buen comportamiento con fluidos viscosos.")

            elif tech == PumpTechnology.PISTON_NEUMATICO:
                # Bomba de piston de aire (tipo ARO 4-ball/AFX): pensada para
                # trasegar fluidos de media/alta viscosidad (pinturas, colas,
                # adhesivos, lacas) directamente desde bidon, con un
                # comportamiento de caudal bastante mas continuo que una
                # neumatica de doble membrana (varias bolas de retencion
                # amortiguan el pulso). Como la AODD, funciona con aire
                # comprimido -> no necesita electricidad, apta en ATEX.
                if req.viscosity_cp > 50:
                    reasons.append(
                        "Diseñada para fluidos de media/alta viscosidad (pinturas, "
                        "colas, adhesivos) trasegados directamente desde bidon."
                    )
                if not req.requires_continuous_flow or req.viscosity_cp > 50:
                    reasons.append(
                        "Caudal bastante mas continuo que una neumatica de doble "
                        "membrana (varias bolas de retencion amortiguan el pulso)."
                    )
                reasons.append("No necesita electricidad: apta en zona ATEX sin instalacion electrica.")
                if req.is_abrasive:
                    warnings.append(
                        "Tolera algo de abrasion (recubrimiento ceramico en el eje/cilindro "
                        "de muchos modelos), pero para abrasivos importantes una peristaltica "
                        "o un tornillo helicoidal desgastan menos."
                    )
                if req.has_solids:
                    suitable = False
                    warnings.append(
                        "Las valvulas de bola de la bomba de piston pueden atascarse con "
                        "solidos en suspension de tamaño apreciable."
                    )

            # --- Puntuacion ---
            score = _TYPICAL_EFFICIENCY[tech] * 0.5
            if suitable:
                score += 0.3
            score += 0.2 * len(reasons) / 3.0
            score -= 0.05 * len(warnings)
            score -= shear_penalty

            # encaje con perfil de inversion (coste relativo)
            cost_rank = _RELATIVE_COST[tech]
            if profile == InvestmentProfile.BARATA and cost_rank <= 1:
                score += 0.1
            elif profile == InvestmentProfile.PREMIUM and cost_rank >= 3:
                score += 0.1
            elif profile == InvestmentProfile.CALIDAD_PRECIO and cost_rank in (2, 3):
                score += 0.1

            score = max(0.0, min(1.0, round(score, 3)))

            results.append(TechnologyRecommendation(
                technology=tech, suitable=suitable, score=score,
                reasons=reasons, warnings=warnings,
            ))

        results.sort(key=lambda r: (r.suitable, r.score), reverse=True)
        return results

    @classmethod
    def allowed_technologies(
        cls,
        req: HydraulicCalculationRequest,
        profile: InvestmentProfile = InvestmentProfile.CALIDAD_PRECIO,
    ) -> List[PumpTechnology]:
        """Solo las tecnologias fisicamente aptas, mejor puntuada primero.
        Si ninguna es apta (caso raro), devuelve todas para no bloquear la
        busqueda — mejor una bomba con aviso que ninguna bomba."""
        evaluated = cls.evaluate(req, profile)
        suitable = [r.technology for r in evaluated if r.suitable]
        return suitable if suitable else [r.technology for r in evaluated]
