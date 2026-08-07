"""Seed de bombas (3 perfiles) y usuario admin interno."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.database import SessionLocal, engine, Base
from app.db.models import PumpModel, UserModel
from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    if not db.query(PumpModel).first():
        catalog = [
            PumpModel(
                id="B-CHEAP-01", brand="Generic Industrial", model="GI-C 40-125",
                technology="Centrifuga con cierre mecanico", profile="BARATA",
                min_flow_m3h=5.0, max_flow_m3h=30.0, max_head_m=30.0,
                base_cost_eur=2800.0, is_atex=False,
                description="Materiales estandar, eficiencia basica.",
                recommended_motor_kw=1.5, match_score=0.70,
            ),
            PumpModel(
                id="EPI-MAG-PRO-40-160", brand="Finish Thompson (FTI)", model="EPI-MAG-PRO 40-160",
                technology="Centrifuga de Acoplamiento Magnetico", profile="CALIDAD_PRECIO",
                min_flow_m3h=5.0, max_flow_m3h=40.0, max_head_m=35.0,
                base_cost_eur=5100.0, is_atex=False,
                description="Fugas cero. Estanqueidad absoluta para fluidos toxicos, sosa o corrosivos.",
                recommended_motor_kw=1.5, match_score=0.94,
            ),
            PumpModel(
                id="B-QP-02", brand="KSB", model="Etabloc 050-032-160",
                technology="Centrifuga con cierre mecanico", profile="CALIDAD_PRECIO",
                min_flow_m3h=10.0, max_flow_m3h=60.0, max_head_m=35.0,
                base_cost_eur=4200.0, is_atex=True,
                description="Componentes reforzados, sellados de alta gama.",
                recommended_motor_kw=2.2, match_score=0.88,
            ),
            PumpModel(
                id="B-PREM-01", brand="Sundyne", model="ANTARES Mag-Drive 50",
                technology="Centrifuga de Acoplamiento Magnetico", profile="PREMIUM",
                min_flow_m3h=5.0, max_flow_m3h=50.0, max_head_m=50.0,
                base_cost_eur=9800.0, is_atex=True,
                description="Tecnologia de vanguardia, alta resistencia quimica/mecanica.",
                recommended_motor_kw=2.2, match_score=0.96,
            ),
            PumpModel(
                id="B-PREM-02", brand="Verder", model="Verderflex VF65",
                technology="Peristaltica", profile="PREMIUM",
                min_flow_m3h=0.5, max_flow_m3h=20.0, max_head_m=25.0,
                base_cost_eur=7500.0, is_atex=True,
                description="Dosificacion de alta precision, fluidos sensibles al cizallamiento.",
                recommended_motor_kw=1.5, match_score=0.85,
            ),
            PumpModel(
                id="B-CHEAP-02", brand="Tapflo", model="T100",
                technology="Neumatica de Doble Membrana", profile="BARATA",
                min_flow_m3h=1.0, max_flow_m3h=15.0, max_head_m=80.0,
                base_cost_eur=1200.0, is_atex=True,
                description="Neumatica economica para fluidos viscosos o ATEX.",
                recommended_motor_kw=0.0, match_score=0.65,
            ),
        ]
        db.add_all(catalog)
        print(f"Insertadas {len(catalog)} bombas.")
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
