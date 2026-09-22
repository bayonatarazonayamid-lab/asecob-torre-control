"""
Catálogos Redelex para plantilla Excel y radicación (nuevo.asp).

Fuente: inspectores DOM aportados por el equipo (ciudad_juzgado, tipo despacho).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_BASE = Path(__file__).resolve().parent
_TSV_CIUDADES = _BASE / "catalogos" / "ciudades_juzgado.tsv"
_TXT_TIPOS = _BASE / "catalogos" / "tipos_juzgado.txt"


@lru_cache(maxsize=1)
def _cargar_ciudades() -> Tuple[Tuple[str, str], ...]:
    if not _TSV_CIUDADES.exists():
        return tuple()
    filas: List[Tuple[str, str]] = []
    for linea in _TSV_CIUDADES.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or "\t" not in linea:
            continue
        valor, etiqueta = linea.split("\t", 1)
        filas.append((valor.strip(), etiqueta.strip()))
    return tuple(filas)


@lru_cache(maxsize=1)
def _cargar_tipos_juzgado() -> Tuple[str, ...]:
    if not _TXT_TIPOS.exists():
        return (
            "JUZGADO CIVIL MUNICIPAL",
            "JUZGADO CIVIL DEL CIRCUITO",
            "JUZGADO PROMISCUO MUNICIPAL",
            "JUZGADO PROMISCUO DEL CIRCUITO",
            "SIN ESPECIFICAR",
        )
    return tuple(
        ln.strip()
        for ln in _TXT_TIPOS.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    )


def etiquetas_ciudades() -> List[str]:
    return [et for _, et in _cargar_ciudades()]


def etiquetas_tipos_juzgado() -> List[str]:
    return list(_cargar_tipos_juzgado())


def mapa_ciudad_etiqueta_a_valor() -> Dict[str, str]:
    return {et.upper(): val for val, et in _cargar_ciudades()}


def mapa_ciudad_valor_a_etiqueta() -> Dict[str, str]:
    return {val: et for val, et in _cargar_ciudades()}


def resolver_valor_ciudad(texto: Optional[str]) -> Optional[str]:
    """
    Acepta etiqueta completa, value numérico, o coincidencia parcial.
    Devuelve el value de Redelex o None.
    """
    if texto is None:
        return None
    raw = str(texto).strip()
    if not raw:
        return None
    # Value directo
    por_valor = mapa_ciudad_valor_a_etiqueta()
    if raw in por_valor:
        return raw
    if raw.isdigit() and raw in por_valor:
        return raw

    por_et = mapa_ciudad_etiqueta_a_valor()
    key = raw.upper()
    if key in por_et:
        return por_et[key]

    # Coincidencia parcial (ej. "PEREIRA" o "PEREIRA - RISARALDA")
    for etiqueta, valor in por_et.items():
        if key in etiqueta or etiqueta.startswith(key):
            return valor
    return None


def resolver_tipo_juzgado(texto: Optional[str]) -> Optional[str]:
    if texto is None:
        return None
    raw = str(texto).strip()
    if not raw:
        return None
    key = raw.upper()
    for et in _cargar_tipos_juzgado():
        if et.upper() == key:
            return et
    for et in _cargar_tipos_juzgado():
        if key in et.upper() or et.upper() in key:
            return et
    return raw  # el robot intentará select por label tal cual
