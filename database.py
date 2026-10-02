"""Configuración SQLAlchemy: SQLite local por defecto; PostgreSQL vía DATABASE_URL."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL


def _sqlalchemy_url(url: str) -> str:
    """
    SQLAlchemy 2.1+ trata postgresql:// como psycopg (v3).
    Este proyecto usa psycopg2-binary → forzar el dialecto explícito.
    """
    u = (url or "").strip()
    if u.startswith("postgresql+psycopg2://") or u.startswith("postgresql+psycopg://"):
        return u
    if u.startswith("postgresql://"):
        return "postgresql+psycopg2://" + u[len("postgresql://") :]
    if u.startswith("postgres://"):
        return "postgresql+psycopg2://" + u[len("postgres://") :]
    return u


_URL = _sqlalchemy_url(DATABASE_URL)
connect_args = {"check_same_thread": False} if _URL.startswith("sqlite") else {}
engine = create_engine(_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
