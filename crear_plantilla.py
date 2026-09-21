"""
Generador de la plantilla Excel inteligente de radicación.
Listas desplegables (xlsxwriter) + hoja oculta de catálogos.
"""
from __future__ import annotations

import io
from typing import BinaryIO, List

import xlsxwriter

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
    "Estado_Robot",
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

    for idx, col in enumerate(COLUMNAS):
        ws.write(0, idx, col, header_fmt)
        ws.set_column(idx, idx, max(18, len(col) + 2))

    _escribir_lista(oculto, 0, TIPOS_ID, "TipoId")
    _escribir_lista(oculto, 1, CARTERAS, "Carteras")
    _escribir_lista(oculto, 2, TIPOS_BIEN, "Bienes")
    _escribir_lista(oculto, 3, TIPOS_INTERVENCION, "Intervencion")

    max_filas = 500
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

    # Fila de ejemplo (el usuario puede borrar o sobrescribir)
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
        "PENDIENTE",
    ]
    for idx, valor in enumerate(ejemplo):
        if idx in (11, 12):
            ws.write(1, idx, valor, fecha_fmt)
        elif idx == 13:
            ws.write_number(1, idx, float(valor), dinero_fmt)
        else:
            ws.write(1, idx, valor, ejemplo_fmt)

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
