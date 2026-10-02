"""Configuración SQLAlchemy: SQLite local por defecto; PostgreSQL vía DATABASE_URL."""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL


def _sqlalchemy_url(url: str) -> str:
    """
    SQLAlchemy 2.1+ trata postgresql:// como psycopg (v3).
    Este proyecto usa psycopg2-binary → forzar el dialecto explícito.
    """
    u = (url or "").strip()
    # Quitar comillas si las pegaron en Render
    if (u.startswith('"') and u.endswith('"')) or (u.startswith("'") and u.endswith("'")):
        u = u[1:-1].strip()
    if u.startswith("postgresql+psycopg2://") or u.startswith("postgresql+psycopg://"):
        return u
    if u.startswith("postgresql://"):
        return "postgresql+psycopg2://" + u[len("postgresql://") :]
    if u.startswith("postgres://"):
        return "postgresql+psycopg2://" + u[len("postgres://") :]
    return u


_URL = _sqlalchemy_url(DATABASE_URL or "")
_ENV_RAW = (os.getenv("DATABASE_URL") or "").strip()

# Si en Render hay DATABASE_URL de Postgres pero el engine caería en sqlite → error explícito
if _ENV_RAW and ("postgres" in _ENV_RAW.lower() or "neon.tech" in _ENV_RAW.lower()):
    if not _URL.startswith("postgresql"):
        print(
            f"[BD] ERROR: DATABASE_URL de entorno no se interpretó como Postgres.\n"
            f"  crudo[:40]={_ENV_RAW[:40]!r}\n"
            f"  resuelto[:40]={_URL[:40]!r}",
            file=sys.stderr,
            flush=True,
        )
        raise RuntimeError("DATABASE_URL inválida: se esperaba postgresql://…")

connect_args = {"check_same_thread": False} if _URL.startswith("sqlite") else {}
engine = create_engine(_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Log inmediato al importar (aparece en Render Logs)
try:
    _host = engine.url.host or "(local)"
    _db = engine.url.database or ""
    print(
        f"[BD] dialect={engine.dialect.name} host={_host} db={_db}",
        flush=True,
    )
except Exception as e:
    print(f"[BD] No se pudo describir engine: {e}", flush=True)
