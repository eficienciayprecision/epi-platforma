"""Conexion a base de datos: PostgreSQL (Docker/produccion) o SQLite (local sin Docker)."""
from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Por defecto usa un fichero SQLite local (epi_local.db) para poder probar
# sin Docker ni PostgreSQL instalados. En produccion se sobreescribe con
# DATABASE_URL=postgresql://... (ver docker-compose.yml).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./epi_local.db")

# Render (y Heroku, de donde viene esta convencion) entrega las URL de
# PostgreSQL con el prefijo "postgres://", pero SQLAlchemy 2.x ya no lo
# reconoce como dialecto valido (hace falta "postgresql://") — sin esto,
# la app no arrancaria si se pega la URL de Render tal cual.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
