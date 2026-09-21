"""Autenticación simple para Torre de Control en internet."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from config import getenv

ASECOB_API_KEY = getenv("ASECOB_API_KEY")
DASHBOARD_PASSWORD = getenv("DASHBOARD_PASSWORD")
security_basic = HTTPBasic(auto_error=False)
SESSION_COOKIE = "asecob_session"


def token_sesion(password: str) -> str:
    return hmac.new(b"asecob-torre", password.encode(), hashlib.sha256).hexdigest()


def _sesion_valida(valor: Optional[str]) -> bool:
    if not DASHBOARD_PASSWORD or not valor:
        return False
    return hmac.compare_digest(valor, token_sesion(DASHBOARD_PASSWORD))


def _basic_dashboard_ok(credentials: Optional[HTTPBasicCredentials]) -> bool:
    if not DASHBOARD_PASSWORD or not credentials:
        return False
    return credentials.username == "asecob" and hmac.compare_digest(
        credentials.password, DASHBOARD_PASSWORD
    )


def acceso_dashboard_ok(request: Request, credentials: Optional[HTTPBasicCredentials] = None) -> bool:
    """True si el visitante puede ver el tablero (sin lanzar 401)."""
    if not DASHBOARD_PASSWORD:
        return True
    if _sesion_valida(request.cookies.get(SESSION_COOKIE)):
        return True
    if _basic_dashboard_ok(credentials):
        return True
    return False


def verificar_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    api_key: Optional[str] = Query(default=None, alias="api_key"),
    credentials: Optional[HTTPBasicCredentials] = Depends(security_basic),
) -> None:
    """
    Protege /api/* cuando ASECOB_API_KEY está definida.
    Acepta: X-API-Key (robots) O login del dashboard (abogados en navegador).
    """
    if not ASECOB_API_KEY and not DASHBOARD_PASSWORD:
        return

    proporcionada = x_api_key or api_key
    if ASECOB_API_KEY and proporcionada and hmac.compare_digest(proporcionada, ASECOB_API_KEY):
        return

    if _basic_dashboard_ok(credentials):
        return

    if _sesion_valida(request.cookies.get(SESSION_COOKIE)):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autorizado. Robots: envíe X-API-Key. Abogados: inicie sesión en el tablero.",
        headers={"WWW-Authenticate": 'Basic realm="Asecob Torre de Control"'},
    )


def verificar_acceso_dashboard(
    request: Request,
    credentials: Optional[HTTPBasicCredentials] = Depends(security_basic),
    token: Optional[str] = Query(default=None),
) -> None:
    if not DASHBOARD_PASSWORD:
        return

    if token and hmac.compare_digest(token, DASHBOARD_PASSWORD):
        return
    if acceso_dashboard_ok(request, credentials):
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Acceso al dashboard restringido.",
        headers={"WWW-Authenticate": 'Basic realm="Asecob Torre de Control"'},
    )


def generar_api_key_sugerida() -> str:
    return secrets.token_urlsafe(24)
