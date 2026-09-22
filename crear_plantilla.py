"""
Generador de la plantilla Excel inteligente de radicación.
Listas desplegables (xlsxwriter) + hoja oculta de catálogos.
Incluye Radicacion, Tipo_Juzgado, Numero_Juzgado, Ciudad_Juzgado.
"""
from __future__ import annotations

import io
from typing import BinaryIO, List

import xlsxwriter

from catalogos_redelex import etiquetas_ciudades, etiquetas_tipos_juzgado

CARTERAS = [
    "CONJUNTOS RESIDENCIALES",
    "REENCAFE",
    "YAMID BAYONA",
    "CREDITOS SAS",
    "GRUPO ASECOB",
    "FONDO DE GARANTIAS",
    "COMFAMILIAR",
    "FINANFUTURO",
    "FUNDACION AMANECER",
    "SUZUKI",
    "GRUPO TROPI",
    "ACTUAR QUINDIO",
    "COMERCIALIZADORA SANTANDER",
    "GEES GLOBAL",
]

TIPOS_ID = ["CC", "CE", "NIT", "PPT", "PA"]
TIPOS_BIEN = ["BANCOS", "VEHICULO", "INMUEBLE", "SALARIOS", "OTRO", "N/A"]
TIPOS_INTERVENCION = ["ASECOB", "CLIENTE", "MIXTO"]

COLUMNAS = [
    "Tipo_Id_Demandado",
    "Identificacion_Demandado",
    "Nombres_Demandado",
    "Apellidos_Demandado",
    "Tipo_Id_Codeudor",
    "Identificacion_Codeudor",
    "Nombres_Codeudor",
    "Apellidos_Codeudor",
    "Cartera_Dropdown",
    "Nombre_Demandante",
    "NIT_Demandante",
    "Fecha_Ingreso_Cartera",
    "Fecha_Presentacion_Demanda",
    "Monto_Pretension",
    "Tipo_Bien_Medida",
    "Descripcion_Medida",
    "Tipo_Intervencion",
    # Redelex nuevo.asp — entre radicación y Guardar
    "Radicacion",
    "Referencia",
    "Clase_Proceso",
    "Tipo_Juzgado",
    "Numero_Juzgado",
    "Ciudad_Juzgado",
    "Estado_Robot",
]

CLASES_PROCESO = [
    "EJECUTIVO",
    "EJECUTIVO HIPOTECARIO",
    "EJECUTIVO PRENDARIO",
    "VERBAL",
    "ABREVIADO",
    "LABORAL ORDINARIO",
    "ACCION DE TUTELA",
    "CONCILIACION PREJUDICIAL",
    "-- SIN ESPECIFICAR --",
]


def _escribir_lista(ws, col: int, valores: List[str], encabezado: str) -> None:
    ws.write(0, col, encabezado)
    for i, valor in enumerate(valores, start=1):
        ws.write(i, col, valor)


def generar_plantilla_bytes() -> bytes:
    buffer = io.BytesIO()
    wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
    ws = wb.add_worksheet("Radicacion")
    oculto = wb.add_worksheet("_catalogos")
    oculto.hide()

    header_fmt = wb.add_format(
        {
            "bold": True,
            "bg_color": "#0f172a",
            "font_color": "#ffffff",
            "border": 1,
        }
    )
    fecha_fmt = wb.add_format({"num_format": "yyyy-mm-dd"})
    dinero_fmt = wb.add_format({"num_format": "#,##0"})
    ejemplo_fmt = wb.add_format({"font_color": "#64748b", "italic": True})
    nota_fmt = wb.add_format({"font_color": "#0f2f61", "italic": True})

    for idx, col in enumerate(COLUMNAS):
        ws.write(0, idx, col, header_fmt)
        ws.set_column(idx, idx, max(18, len(col) + 2))

    tipos_juzgado = etiquetas_tipos_juzgado()
    ciudades = etiquetas_ciudades()

    _escribir_lista(oculto, 0, TIPOS_ID, "TipoId")
    _escribir_lista(oculto, 1, CARTERAS, "Carteras")
    _escribir_lista(oculto, 2, TIPOS_BIEN, "Bienes")
    _escribir_lista(oculto, 3, TIPOS_INTERVENCION, "Intervencion")
    _escribir_lista(oculto, 4, tipos_juzgado, "TipoJuzgado")
    _escribir_lista(oculto, 5, ciudades, "Ciudades")
    _escribir_lista(oculto, 6, CLASES_PROCESO, "ClaseProceso")

    max_filas = 500
    # A=Tipo_Id_Demandado, E=Tipo_Id_Codeudor, I=Cartera, O=Tipo_Bien, Q=Tipo_Intervencion
    ws.data_validation(
        f"A2:A{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$A$2:$A${len(TIPOS_ID) + 1}"},
    )
    ws.data_validation(
        f"E2:E{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$A$2:$A${len(TIPOS_ID) + 1}"},
    )
    ws.data_validation(
        f"I2:I{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$B$2:$B${len(CARTERAS) + 1}"},
    )
    ws.data_validation(
        f"O2:O{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$C$2:$C${len(TIPOS_BIEN) + 1}"},
    )
    ws.data_validation(
        f"Q2:Q{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$D$2:$D${len(TIPOS_INTERVENCION) + 1}"},
    )
    # T=Clase_Proceso, U=Tipo_Juzgado, W=Ciudad_Juzgado
    ws.data_validation(
        f"T2:T{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$G$2:$G${len(CLASES_PROCESO) + 1}"},
    )
    ws.data_validation(
        f"U2:U{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$E$2:$E${len(tipos_juzgado) + 1}"},
    )
    # Ciudad: lista larga — Excel limita fórmulas a ~255 chars en source inline;
    # la referencia a hoja oculta soporta miles de filas.
    n_ciudades = max(1, len(ciudades))
    ws.data_validation(
        f"W2:W{max_filas}",
        {"validate": "list", "source": f"=_catalogos!$F$2:$F${n_ciudades + 1}"},
    )

    # Fila de ejemplo
    ejemplo = [
        "CC",
        "1098765432",
        "JUAN CARLOS",
        "PEREZ GOMEZ",
        "",
        "",
        "",
        "",
        "SUZUKI",
        "SUZUKI MOTOR DE COLOMBIA S.A.",
        "890900000",
        "2026-01-15",
        "2026-03-01",
        8500000,
        "VEHICULO",
        "Embargo vehículo placa ABC123",
        "ASECOB",
        "",  # Radicacion vacía → robot marca Sin Número
        "DEMANDADO PEREZ - pretensión ejecutiva",
        "EJECUTIVO",
        "JUZGADO CIVIL MUNICIPAL",
        "0",  # Numero_Juzgado default
        "PEREIRA - RISARALDA",
        "PENDIENTE",
    ]
    for idx, valor in enumerate(ejemplo):
        if idx in (11, 12):
            ws.write(1, idx, valor, fecha_fmt)
        elif idx == 13:
            ws.write_number(1, idx, float(valor), dinero_fmt)
        else:
            ws.write(1, idx, valor, ejemplo_fmt)

    # Nota operativa fila 3
    ws.write(
        2,
        0,
        "NOTA: Si Radicacion queda vacía, el robot marca «Sin Número». "
        "Si Numero_Juzgado queda vacío, se envía 0. "
        "Ciudad_Juzgado y Tipo_Juzgado son listas desplegables.",
        nota_fmt,
    )

    ws.freeze_panes(1, 0)
    wb.close()
    buffer.seek(0)
    return buffer.read()


def escribir_plantilla(destino: BinaryIO) -> None:
    destino.write(generar_plantilla_bytes())


if __name__ == "__main__":
    from pathlib import Path

    out = Path(__file__).resolve().parent / "Plantilla_Radicacion_Inteligente.xlsx"
    out.write_bytes(generar_plantilla_bytes())
    print(f"Plantilla generada: {out}")
    print(f"Ciudades en catálogo: {len(etiquetas_ciudades())}")
    print(f"Tipos juzgado: {len(etiquetas_tipos_juzgado())}")
