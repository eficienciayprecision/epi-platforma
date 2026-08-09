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
}


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if not db.query(PumpModel).first():
        if os.path.exists(CATALOG_CSV):
            catalog = _load_catalog_from_csv(CATALOG_CSV)
            db.add_all(catalog)
            print(f"Insertadas {len(catalog)} bombas desde el catalogo real (pumps_catalog.csv).")
        else:
            print(f"AVISO: no se encontro {CATALOG_CSV}; no se ha insertado ninguna bomba.")
    else:
        print("Catalogo de bombas ya existe.")

    if not db.query(UserModel).first():
        hash_pw = pwd.hash(os.getenv("EPI_ADMIN_SEED_PASSWORD", "changeme-2026"))
        users = [
            UserModel(username="admin", full_name="Administrador EPI", role="admin", hashed_password=hash_pw),
            UserModel(username="ingeniero", full_name="Ingeniero de Proyecto", role="engineer", hashed_password=hash_pw),
        ]
        db.add_all(users)
        print("Insertados usuarios internos (admin, ingeniero). Cambia la contraseña por defecto.")
    else:
        print("Usuarios internos ya existen.")

    db.commit()
    db.close()
    print("Seed completado.")


if __name__ == "__main__":
    seed()
