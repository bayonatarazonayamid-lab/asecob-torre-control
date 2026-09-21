"""Centralizador de variables de entorno para Torre de Control Asecob."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def getenv(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


DATABASE_URL = getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'asecob_legaltech.db'}")
# Render/Heroku a veces entregan postgres:// — SQLAlchemy 2 exige postgresql://
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

API_BASE_URL = getenv("API_BASE_URL", "http://127.0.0.1:8765/api")
URL_API_ESTADOS = getenv("URL_API_ESTADOS", f"{API_BASE_URL}/estados/sincronizar")
PUBLIC_BASE_URL = getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8765")
ASECOB_API_KEY = getenv("ASECOB_API_KEY")
DASHBOARD_PASSWORD = getenv("DASHBOARD_PASSWORD")
MODO_PRUEBAS = getenv("MODO_PRUEBAS", "False").lower() in ("true", "1", "t", "yes")
HEADLESS_MODE = getenv("HEADLESS_MODE", "False").lower() in ("true", "1")

# IA
GEMINI_API_KEY = getenv("GEMINI_API_KEY") or getenv("API_KEY_GEMINI")
GROQ_API_KEY = getenv("GROQ_API_KEY") or getenv("API_KEY_GROQ")

# Correo
CORREO_SISTEMA = getenv("CORREO_SISTEMA", "notificacionesyamidbayona@gmail.com")
GMAIL_APP_PASSWORD = getenv("GMAIL_APP_PASSWORD") or getenv("CLAVE_GMAIL")
CORREO_DEFECTO = getenv("CORREO_DEFECTO", "coordinacion@asecobsas.com")
CORREO_SANDBOX = getenv("CORREO_SANDBOX", "juridico@asecobsas.com")
CORREOS_TODOS_ABOGADOS = getenv(
    "CORREOS_TODOS_ABOGADOS",
    "juridico@asecobsas.com,juridico2@asecobsas.com,juridico3@asecobsas.com,coordinacionjuridica@asecobsas.com",
)

# Portales
USUARIO_RJ = getenv("USUARIO_RJ")
CLAVE_RJ = getenv("CLAVE_RJ")
USUARIO_REDELEX = getenv("USUARIO_REDELEX", "juridico@asecobsas.com")
CLAVE_REDELEX = getenv("CLAVE_REDELEX")

RUTA_CARPETA = getenv("RUTA_CARPETA", str(BASE_DIR / "AUTOS_DESCARGADOS"))
