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
                real_efficiency_pct=float(row["real_efficiency_pct"]) if row.get("real_efficiency_pct") else None,
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
                tipo_componente=row.get("tipo_componente") or None,
                bomba_compatible=row.get("bomba_compatible") or None,
            ))
    return rows


def _migrate_missing_columns():
    """NUEVO — Base.metadata.create_all() SOLO crea tablas que no existen;
    NUNCA añade columnas nuevas a una tabla que ya existe en produccion.
    Cada vez que se añade un campo a un modelo (p.ej. real_efficiency_pct
    en agosto 2026) hay que añadirlo tambien aqui, o la tabla de Jon en
    Render se queda desincronizada del modelo y CUALQUIER consulta a esa
    tabla revienta con "column ... does not exist" — como paso el 11 de
    agosto de 2026, bloqueando ademas la actualizacion de la contraseña de
    los usuarios internos porque el fallo cortaba el arranque antes de
    llegar a esa parte."""
    import sqlalchemy as sa
    inspector = sa.inspect(engine)
    migrations = {
        "pumps_catalog": [("real_efficiency_pct", "FLOAT")],
        "spare_parts_catalog": [("tipo_componente", "VARCHAR"), ("bomba_compatible", "VARCHAR")],
    }
    migrated_tables = set()
    with engine.begin() as conn:
        for table, columns in migrations.items():
            if table not in inspector.get_table_names():
                continue  # la creara create_all() si es tabla nueva
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            for col_name, col_type in columns:
                if col_name not in existing_cols:
                    conn.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_type}"))
                    print(f"Migracion: añadida columna {table}.{col_name} ({col_type}).")
                    migrated_tables.add(table)
    return migrated_tables


def seed():
    Base.metadata.create_all(bind=engine)
    migrated_tables = set()
    try:
        migrated_tables = _migrate_missing_columns()
    except Exception as migration_error:
        print(f"AVISO: fallo en la migracion de columnas (se continua igualmente): {migration_error}")
    db = SessionLocal()

    # PASO 1: catalogo de bombas. Se guarda (commit) de inmediato, ANTES de
    # tocar los usuarios internos — si algo falla mas adelante (como paso
    # con la creacion de usuarios en agosto 2026, un problema de version
    # entre passlib y bcrypt), el catalogo de bombas ya esta a salvo en la
    # base de datos y no se pierde con el resto de la transaccion.
    #
    # FIX (11 agosto 2026) — un fallo aqui (p.ej. columna desincronizada)
    # abortaba TODO el arranque, incluido el paso 2 (usuarios internos) mas
    # abajo, que ni siquiera llegaba a intentarse. Aislado en su propio
    # try/except para que un problema con el catalogo NUNCA pueda bloquear
    # la actualizacion de usuarios.
    try:
        catalog = _load_catalog_from_csv(CATALOG_CSV) if os.path.exists(CATALOG_CSV) else []
        current_count = db.query(PumpModel).count()
    except Exception as catalog_error:
        db.rollback()
        catalog = []
        current_count = None
        print(f"AVISO: no se pudo cargar el catalogo de bombas al arrancar: {catalog_error}")

    if current_count is None:
        pass  # ya se aviso arriba; no se toca el catalogo esta vez
    elif not catalog:
        print(f"AVISO: no se encontro {CATALOG_CSV}; el catalogo actual ({current_count} bombas) no se ha tocado.")
    elif current_count != len(catalog):
        db.query(PumpModel).delete()
        db.add_all(catalog)
        db.commit()
        print(f"Catalogo de bombas actualizado: {current_count} bombas antiguas sustituidas por {len(catalog)} nuevas.")
    else:
        print(f"Catalogo de bombas ya esta actualizado ({current_count} bombas).")

    # PASO 1b: catalogo de repuestos (independiente del de bombas).
    # Aislado igual que el paso 1: un fallo aqui tampoco debe poder
    # bloquear el paso 2 (usuarios internos).
    try:
        from app.db.models import SparePartModel
        spare_parts = _load_spare_parts_from_csv(SPARE_PARTS_CSV) if os.path.exists(SPARE_PARTS_CSV) else []
        current_sp_count = db.query(SparePartModel).count()
        # NUEVO (agosto 2026) — si se acaban de añadir columnas nuevas a esta
        # tabla (p.ej. tipo_componente/bomba_compatible), las filas ya
        # existentes se quedarian con esas columnas a NULL para siempre,
        # porque el numero de filas no cambia y por tanto nunca se cumpliria
        # la condicion de "recargar". Forzamos una recarga completa esa vez.
        needs_reload = "spare_parts_catalog" in migrated_tables
        if not spare_parts:
            print(f"AVISO: no se encontro {SPARE_PARTS_CSV}; catalogo de repuestos ({current_sp_count}) no tocado.")
        elif current_sp_count != len(spare_parts) or needs_reload:
            db.query(SparePartModel).delete()
            db.add_all(spare_parts)
            db.commit()
            reason = "columnas nuevas migradas" if needs_reload and current_sp_count == len(spare_parts) else f"{current_sp_count} antiguos sustituidos por {len(spare_parts)} nuevos"
            print(f"Catalogo de repuestos actualizado: {reason}.")
        else:
            print(f"Catalogo de repuestos ya esta actualizado ({current_sp_count} repuestos).")
    except Exception as spare_error:
        db.rollback()
        print(f"AVISO: no se pudo cargar el catalogo de repuestos al arrancar: {spare_error}")

    # PASO 2: usuarios internos. Aislado en su propio try/except: un fallo
    # aqui (p.ej. de compatibilidad de bcrypt) no debe poder deshacer ni
    # bloquear el paso 1, que ya quedo guardado.
    #
    # NUEVO — antes esto solo insertaba admin/ingeniero si la tabla estaba
    # VACIA, así que cambiar la contraseña por defecto en el codigo no
    # tenia ningun efecto en una base de datos que ya tenia esos usuarios
    # creados (el caso de Jon en produccion). Ahora se actualiza la
    # contraseña de admin/ingeniero en cada arranque si siguen teniendo la
    # contraseña por defecto de fabrica — si Jon ya la hubiera cambiado a
    # otra cosa por su cuenta, no se toca.
    try:
        seed_password = os.getenv("EPI_ADMIN_SEED_PASSWORD", "Epi1618++Render")
        factory_default = "changeme-2026"
        existing = {u.username: u for u in db.query(UserModel).filter(
            UserModel.username.in_(["admin", "ingeniero"])
        ).all()}

        if not existing:
            hash_pw = pwd.hash(seed_password)
            users = [
                UserModel(username="admin", full_name="Administrador EPI", role="admin", hashed_password=hash_pw),
                UserModel(username="ingeniero", full_name="Ingeniero de Proyecto", role="engineer", hashed_password=hash_pw),
            ]
            db.add_all(users)
            db.commit()
            print("Insertados usuarios internos (admin, ingeniero) con la contraseña configurada.")
        else:
            updated = 0
            for username in ("admin", "ingeniero"):
                user = existing.get(username)
                if user is None:
                    hash_pw = pwd.hash(seed_password)
                    db.add(UserModel(
                        username=username,
                        full_name="Administrador EPI" if username == "admin" else "Ingeniero de Proyecto",
                        role="admin" if username == "admin" else "engineer",
                        hashed_password=hash_pw,
                    ))
                    updated += 1
                    continue
                try:
                    still_default = pwd.verify(factory_default, user.hashed_password)
                except Exception:
                    still_default = False
                if still_default:
                    user.hashed_password = pwd.hash(seed_password)
                    updated += 1
            if updated:
                db.commit()
                print(f"Contraseña de usuarios internos actualizada ({updated} usuario(s)).")
            else:
                print("Usuarios internos ya existen con una contraseña ya personalizada (no se toca).")
    except Exception as user_seed_error:
        db.rollback()
        print(f"AVISO: no se pudieron crear/actualizar los usuarios internos (el catalogo de bombas SI se guardo bien): {user_seed_error}")

    db.close()
    print("Seed completado.")


if __name__ == "__main__":
    seed()
