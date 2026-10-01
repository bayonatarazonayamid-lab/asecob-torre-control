"""
Motor de reglas del Cartero.
Usado por la Torre (validación) y por robot_correo (evaluación local).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

TIPOS_MATCH = ("CORREO", "DOMINIO", "ASUNTO")
# ASIGNAR_A = enviar siempre a un abogado concreto (campo asignado_a obligatorio)
ACCIONES = ("IGNORAR", "ALERTA_MANUAL", "BUSCAR_RADICADO", "ASIGNAR_A")

# Destinos frecuentes del estudio (para el selector del Dashboard)
ABOGADOS_DESTINO: List[Dict[str, str]] = [
    {"email": "juridico@asecobsas.com", "etiqueta": "Jurídico 1"},
    {"email": "juridico2@asecobsas.com", "etiqueta": "Jurídico 2"},
    {"email": "juridico3@asecobsas.com", "etiqueta": "Jurídico 3"},
    {"email": "coordinacionjuridica@asecobsas.com", "etiqueta": "Coordinación jurídica"},
    {"email": "coordinacion@asecobsas.com", "etiqueta": "Coordinación"},
]

ACCIONES_LABEL = {
    "IGNORAR": "Ignorar (no reenviar)",
    "ALERTA_MANUAL": "Avisar para revisión manual",
    "BUSCAR_RADICADO": "Procesar como providencia",
    "ASIGNAR_A": "Enviar siempre a este abogado",
}

TIPOS_LABEL = {
    "CORREO": "Remitente = este correo",
    "DOMINIO": "Remitente de este dominio",
    "ASUNTO": "Asunto contiene…",
}

# Semilla alineada con las exclusiones históricas del código
REGLAS_DEFAULT: List[Dict[str, Any]] = [
    {
        "nombre": "Buzón propio del robot",
        "tipo_match": "CORREO",
        "patron": "notificacionesyamidbayona@gmail.com",
        "accion": "IGNORAR",
        "prioridad": 10,
        "notas": "Evita bucles con el propio reenvío",
    },
    {
        "nombre": "Contabilidad Sol de Galicia",
        "tipo_match": "CORREO",
        "patron": "soldegaliciacontabilidad2025@gmail.com",
        "accion": "IGNORAR",
        "prioridad": 10,
        "notas": "Ruido operativo — no reenviar a jurídicos",
    },
    {
        "nombre": "Autorespuesta / fuera de oficina",
        "tipo_match": "ASUNTO",
        "patron": "RESPUESTA AUTOMATICA",
        "accion": "IGNORAR",
        "prioridad": 20,
        "notas": "También cubre variantes sin tilde",
    },
    {
        "nombre": "Autorespuesta (auto respuesta)",
        "tipo_match": "ASUNTO",
        "patron": "AUTO RESPUESTA",
        "accion": "IGNORAR",
        "prioridad": 20,
    },
    {
        "nombre": "Autorespuesta (sin espacio)",
        "tipo_match": "ASUNTO",
        "patron": "AUTORESPUESTA",
        "accion": "IGNORAR",
        "prioridad": 20,
    },
    {
        "nombre": "Out of office",
        "tipo_match": "ASUNTO",
        "patron": "OUT OF OFFICE",
        "accion": "IGNORAR",
        "prioridad": 20,
    },
    {
        "nombre": "Fuera de oficina",
        "tipo_match": "ASUNTO",
        "patron": "FUERA DE OFICINA",
        "accion": "IGNORAR",
        "prioridad": 20,
    },
    {
        "nombre": "Código de verificación",
        "tipo_match": "ASUNTO",
        "patron": "CODIGO DE VERIFICACION",
        "accion": "IGNORAR",
        "prioridad": 20,
    },
    {
        "nombre": "Token validación",
        "tipo_match": "ASUNTO",
        "patron": "TOKEN VALIDACION",
        "accion": "IGNORAR",
        "prioridad": 20,
    },
    {
        "nombre": "Automatic reply",
        "tipo_match": "ASUNTO",
        "patron": "AUTOMATIC REPLY",
        "accion": "IGNORAR",
        "prioridad": 20,
    },
    {
        "nombre": "CENDOJ — buscar radicado",
        "tipo_match": "DOMINIO",
        "patron": "cendoj.ramajudicial.gov.co",
        "accion": "BUSCAR_RADICADO",
        "prioridad": 50,
        "notas": "Flujo normal de providencias CENDOJ",
        "asignado_a": None,
    },
]


def normalizar_texto(texto: str) -> str:
    t = str(texto or "").upper()
    return (
        t.replace("Á", "A")
        .replace("É", "E")
        .replace("Í", "I")
        .replace("Ó", "O")
        .replace("Ú", "U")
        .replace("Ü", "U")
    )


def extraer_email(remitente: str) -> str:
    """Saca user@dominio de un From tipo 'Nombre <user@dom.com>'."""
    import re

    m = re.search(r"([\w.+-]+@[\w.-]+\.\w+)", remitente or "", re.I)
    return (m.group(1) if m else (remitente or "")).strip().lower()


def extraer_dominio(remitente: str) -> str:
    email = extraer_email(remitente)
    if "@" in email:
        return email.split("@", 1)[1].lower().lstrip("@")
    return ""


def validar_regla(
    tipo_match: str,
    accion: str,
    patron: str,
    asignado_a: Optional[str] = None,
) -> Optional[str]:
    tm = (tipo_match or "").strip().upper()
    ac = (accion or "").strip().upper()
    pat = (patron or "").strip()
    asig = (asignado_a or "").strip()
    if tm not in TIPOS_MATCH:
        return f"tipo_match inválido. Use: {', '.join(TIPOS_MATCH)}"
    if ac not in ACCIONES:
        return f"accion inválida. Use: {', '.join(ACCIONES)}"
    if not pat:
        return "El patrón no puede estar vacío"
    if tm == "CORREO" and "@" not in pat:
        return "Para tipo CORREO el patrón debe ser un email (user@dominio)"
    if ac == "ASIGNAR_A":
        if not asig or "@" not in asig:
            return "Para «Enviar a este abogado» debe indicar el email del abogado"
    return None


def _match_regla(regla: Dict[str, Any], remitente: str, asunto: str) -> bool:
    tipo = str(regla.get("tipo_match") or "").upper()
    patron = str(regla.get("patron") or "").strip()
    if not patron:
        return False

    if tipo == "CORREO":
        email = extraer_email(remitente)
        return email == patron.lower() or patron.lower() in (remitente or "").lower()

    if tipo == "DOMINIO":
        dom = extraer_dominio(remitente)
        p = patron.lower().lstrip("@")
        return dom == p or dom.endswith("." + p) or p in (remitente or "").lower()

    if tipo == "ASUNTO":
        return normalizar_texto(patron) in normalizar_texto(asunto)

    return False


def evaluar_reglas(
    reglas: Sequence[Dict[str, Any]],
    remitente: str,
    asunto: str,
) -> Optional[Dict[str, Any]]:
    """
    Primera regla activa que coincida, ordenada por prioridad ASC luego id.
    Devuelve el dict de la regla o None.
    """
    activas = [r for r in reglas if r.get("activo", True)]
    ordenadas = sorted(
        activas,
        key=lambda r: (int(r.get("prioridad") or 100), int(r.get("id") or 0)),
    )
    for regla in ordenadas:
        if _match_regla(regla, remitente, asunto):
            return regla
    return None


def regla_a_dict(obj: Any) -> Dict[str, Any]:
    """ORM o dict → dict plano para el motor."""
    if isinstance(obj, dict):
        return obj
    return {
        "id": getattr(obj, "id", None),
        "nombre": getattr(obj, "nombre", ""),
        "tipo_match": getattr(obj, "tipo_match", ""),
        "patron": getattr(obj, "patron", ""),
        "accion": getattr(obj, "accion", ""),
        "asignado_a": getattr(obj, "asignado_a", None),
        "prioridad": getattr(obj, "prioridad", 100),
        "activo": getattr(obj, "activo", True),
        "notas": getattr(obj, "notas", None),
    }
