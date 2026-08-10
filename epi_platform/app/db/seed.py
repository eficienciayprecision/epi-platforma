"""Seed de bombas (catalogo real EPi) y usuario admin interno.

V7: el catalogo de 6 bombas de ejemplo se sustituye por el catalogo real
de EPi (app/db/pumps_catalog.csv), 1.509 bombas de 5 fabricantes (ARO,
Pompe Cucchi, Sydex, Verderflex, CDR Pompe) con caudal verificado,
construido a partir de las tarifas 2026 de los proveedores y de las fichas
tecnicas publicas de cada fabricante. Ver notas de metodologia en el propio
CSV / conversacion de origen: cada fila incluye caudal min/max, altura
maxima (derivada de la presion de catalogo), potencia de motor cuando se
conoce, y una puntuacion (match_score) que es la eficiencia real calculada
cuando se pudo, o un valor tipico de la tecnologia cuando no.
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.database import SessionLocal, engine, Base
from app.db.models import PumpModel, UserModel
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

CATALOG_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pumps_catalog.csv")


def _load_catalog_from_csv(path: str) -> list[PumpModel]:
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(PumpModel(
                id=row["id"],
                brand=row["brand"],
                model=row["model"],
                technology=_TECH_LABELS.get(row["technology"], row["technology"]),
                profile=row["profile"],
                min_flow_m3h=float(row["min_flow_m3h"]),
                max_flow_m3h=float(row["max_flow_m3h"]),
                max_head_m=float(row["max_head_m"]),
                base_cost_eur=float(row["base_cost_eur"]),
                is_atex=row["is_atex"].strip().lower() in ("true", "1", "yes"),
                description=row["description"],
                recommended_motor_kw=float(row["recommended_motor_kw"]) if row["recommended_motor_kw"] else 1.5,
                motor_voltage=row["motor_voltage"],
                match_score=float(row["match_score"]),
                wetted_body_material=row.get("wetted_body_material") or None,
                wetted_elastomer_material=row.get("wetted_elastomer_material") or None,
                curve_reference_url=row.get("curve_reference_url") or None,
            ))
    return rows


# El CSV guarda el nombre corto del enum (p.ej. "ENGRANAJES"); PumpModel.technology
# guarda el VALOR textual del enum (p.ej. "Engranajes"), igual que hacia el seed
# original y que espera pump_row_to_selected() en main.py.
_TECH_LABELS = {
    "CENTRIFUGA_MECANICO": "Centrifuga con cierre mecanico",
    "CENTRIFUGA_MAGNETICO": "Centrifuga de Acoplamiento Magnetico",
    "NEUMATICA_DOBLE_MEMBRANA": "Neumatica de Doble Membrana",
    "PERISTALTICA": "Peristaltica",
    "TORNILLO_HELICOIDAL": "Tornillo Helicoidal",
    "ENGRANAJES": "Engranajes",
    "PISTON_NEUMATICO": "Pistón Neumático",
}


SPARE_PARTS_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repuestos_catalog.csv")


def _load_spare_parts_from_csv(path: str) -> list:
    from app.db.models import SparePartModel
    rows = []
    seen = set()
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ref = row["referencia"].strip()
            if not ref or ref in seen:
                continue  # referencias duplicadas en el origen: se queda la primera
            seen.add(ref)
            rows.append(SparePartModel(
                referencia=ref,
                descripcion=row["descripcion"],
                fabricante=row["fabricante"],
                precio_eur=float(row["precio_eur"]),
            ))
    return rows


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # PASO 1: catalogo de bombas. Se guarda (commit) de inmediato, ANTES de
    # tocar los usuarios internos — si algo falla mas adelante (como paso
    # con la creacion de usuarios en agosto 2026, un problema de version
    # entre passlib y bcrypt), el catalogo de bombas ya esta a salvo en la
    # base de datos y no se pierde con el resto de la transaccion.
    catalog = _load_catalog_from_csv(CATALOG_CSV) if os.path.exists(CATALOG_CSV) else []
    current_count = db.query(PumpModel).count()

    if not catalog:
        print(f"AVISO: no se encontro {CATALOG_CSV}; el catalogo actual ({current_count} bombas) no se ha tocado.")
    elif current_count != len(catalog):
        db.query(PumpModel).delete()
        db.add_all(catalog)
        db.commit()
        print(f"Catalogo de bombas actualizado: {current_count} bombas antiguas sustituidas por {len(catalog)} nuevas.")
    else:
        print(f"Catalogo de bombas ya esta actualizado ({current_count} bombas).")

    # PASO 1b: catalogo de repuestos (independiente del de bombas).
    from app.db.models import SparePartModel
    spare_parts = _load_spare_parts_from_csv(SPARE_PARTS_CSV) if os.path.exists(SPARE_PARTS_CSV) else []
    current_sp_count = db.query(SparePartModel).count()
    if not spare_parts:
        print(f"AVISO: no se encontro {SPARE_PARTS_CSV}; catalogo de repuestos ({current_sp_count}) no tocado.")
    elif current_sp_count != len(spare_parts):
        db.query(SparePartModel).delete()
        db.add_all(spare_parts)
        db.commit()
        print(f"Catalogo de repuestos actualizado: {current_sp_count} antiguos sustituidos por {len(spare_parts)} nuevos.")
    else:
        print(f"Catalogo de repuestos ya esta actualizado ({current_sp_count} repuestos).")

    # PASO 2: usuarios internos. Aislado en su propio try/except: un fallo
    # aqui (p.ej. de compatibilidad de bcrypt) no debe poder deshacer ni
    # bloquear el paso 1, que ya quedo guardado.
    try:
        if not db.query(UserModel).first():
            hash_pw = pwd.hash(os.getenv("EPI_ADMIN_SEED_PASSWORD", "changeme-2026"))
            users = [
                UserModel(username="admin", full_name="Administrador EPI", role="admin", hashed_password=hash_pw),
                UserModel(username="ingeniero", full_name="Ingeniero de Proyecto", role="engineer", hashed_password=hash_pw),
            ]
            db.add_all(users)
            db.commit()
            print("Insertados usuarios internos (admin, ingeniero). Cambia la contraseña por defecto.")
        else:
            print("Usuarios internos ya existen.")
    except Exception as user_seed_error:
        db.rollback()
        print(f"AVISO: no se pudieron crear los usuarios internos (el catalogo de bombas SI se guardo bien): {user_seed_error}")

    db.close()
    print("Seed completado.")


if __name__ == "__main__":
    seed()
