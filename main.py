"""
Torre de Control - LegalTech Asecob S.A.S.
Núcleo FastAPI: buzón CENDOJ, estados RedJudicial, cola de radicación Redelex.
"""
from __future__ import annotations

import io
from typing import List, Optional

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, Path, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import models
import schemas
from auth import (
    SESSION_COOKIE,
    acceso_dashboard_ok,
    token_sesion,
    verificar_acceso_dashboard,
    verificar_api_key,
)
from config import getenv
from crear_plantilla import generar_plantilla_bytes
from database import SessionLocal, engine
from reglas_correo_motor import ACCIONES, TIPOS_MATCH, REGLAS_DEFAULT, validar_regla
from sqlalchemy import inspect, text

models.Base.metadata.create_all(bind=engine)


def _asegurar_columnas():
    """Añade columnas nuevas en SQLite/Postgres sin romper datos existentes."""
    insp = inspect(engine)
    if "demandas_nuevas" not in insp.get_table_names():
        return
    columnas = {c["name"] for c in insp.get_columns("demandas_nuevas")}
    nuevas = {
        "motivo_error": "TEXT",
        "radicacion": "VARCHAR(50)",
        "referencia": "TEXT",
        "clase_proceso": "VARCHAR(100)",
        "tipo_juzgado": "VARCHAR(150)",
        "numero_juzgado": "VARCHAR(4)",
        "ciudad_juzgado": "VARCHAR(150)",
    }
    with engine.begin() as conn:
        for nombre, tipo in nuevas.items():
            if nombre not in columnas:
                conn.execute(text(f"ALTER TABLE demandas_nuevas ADD COLUMN {nombre} {tipo}"))


_asegurar_columnas()


def _sembrar_reglas_si_vacio():
    """Primera arrancada: carga reglas base del Cartero."""
    db = SessionLocal()
    try:
        if db.query(models.ReglaCorreo).count() == 0:
            for item in REGLAS_DEFAULT:
                db.add(
                    models.ReglaCorreo(
                        nombre=item["nombre"],
                        tipo_match=item["tipo_match"],
                        patron=item["patron"],
                        accion=item["accion"],
                        asignado_a=item.get("asignado_a"),
                        prioridad=item.get("prioridad", 100),
                        activo=True,
                        notas=item.get("notas"),
                    )
                )
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


_sembrar_reglas_si_vacio()

app = FastAPI(
    title="Torre de Control - GRUPO ASECOB SAS",
    description="Backend centralizado para correo CENDOJ, estados de RedJudicial y radicación en Redelex.",
    version="2.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependencia reutilizable: protege la API cuando ASECOB_API_KEY está en el entorno
ApiAuth = Depends(verificar_api_key)
DashAuth = Depends(verificar_acceso_dashboard)
DASHBOARD_PASSWORD = getenv("DASHBOARD_PASSWORD")
APP_VERSION = "2.5.0"

COLUMNAS_EXCEL_REQUERIDAS = [
    "Tipo_Id_Demandado",
    "Identificacion_Demandado",
    "Nombres_Demandado",
    "Apellidos_Demandado",
    "Cartera_Dropdown",
]

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _celda_str(fila, col: str, default: str = "") -> str:
    valor = fila.get(col, default)
    if pd.isna(valor):
        return default
    texto = str(valor).strip()
    if texto.endswith(".0") and texto.replace(".", "", 1).isdigit():
        return texto.split(".")[0]
    return texto


def _celda_opcional(fila, col: str) -> Optional[str]:
    valor = fila.get(col)
    if pd.isna(valor):
        return None
    texto = _celda_str(fila, col)
    return texto or None


def _celda_fecha(fila, col: str):
    valor = fila.get(col)
    if pd.isna(valor):
        return None
    return pd.to_datetime(valor, errors="coerce")


def _celda_float(fila, col: str, default: float = 0.0) -> float:
    valor = fila.get(col, default)
    if pd.isna(valor):
        return default
    try:
        return float(valor)
    except (TypeError, ValueError):
        return default


@app.get("/health")
@app.get("/api/salud")
def salud_servidor():
    return {
        "estado": "En línea",
        "sistema": "Torre de Control · GRUPO ASECOB SAS",
        "version": APP_VERSION,
        "dashboard": "/dashboard",
        "equipo": "Tablero compartido · robots locales en oficina",
    }


@app.get("/", response_class=HTMLResponse)
def portada(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="inicio.html",
        context={"version": APP_VERSION},
    )


@app.get("/entrar", response_class=HTMLResponse)
def entrar_get(request: Request):
    # Sin clave en Render: no hace falta login
    if not DASHBOARD_PASSWORD:
        return RedirectResponse("/dashboard", status_code=303)
    if acceso_dashboard_ok(request):
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="entrar.html",
        context={
            "error": None,
            "clave_configurada": True,
        },
    )


@app.post("/entrar", response_class=HTMLResponse)
def entrar_post(request: Request, clave: str = Form(...)):
    if not DASHBOARD_PASSWORD:
        return RedirectResponse("/dashboard", status_code=303)
    if clave != DASHBOARD_PASSWORD:
        return templates.TemplateResponse(
            request=request,
            name="entrar.html",
            context={
                "error": "Clave incorrecta. Es la variable DASHBOARD_PASSWORD de Render (Environment).",
                "clave_configurada": True,
            },
            status_code=401,
        )
    respuesta = RedirectResponse("/dashboard", status_code=303)
    respuesta.set_cookie(
        key=SESSION_COOKIE,
        value=token_sesion(clave),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return respuesta


@app.get("/salir")
def salir():
    respuesta = RedirectResponse("/", status_code=303)
    respuesta.delete_cookie(SESSION_COOKIE)
    return respuesta


@app.get("/api/estadisticas", dependencies=[ApiAuth])
def obtener_estadisticas_basicas(db: Session = Depends(get_db)):
    return {
        "notificaciones_correo": db.query(models.Notificacion).count(),
        "estados_redjudicial": db.query(models.ActuacionEstado).count(),
        "demandas_para_radicar": db.query(models.DemandaNueva).count(),
    }


@app.post("/api/notificaciones/", response_model=dict, dependencies=[ApiAuth])
def recibir_notificacion_robot(notificacion: schemas.NotificacionCreate, db: Session = Depends(get_db)):
    nueva_notif = models.Notificacion(
        asunto_original=notificacion.asunto_original,
        remitente=notificacion.remitente,
        clasificacion_ia=notificacion.clasificacion_ia,
        sub_embargo=notificacion.sub_embargo,
        fecha_audiencia=notificacion.fecha_audiencia,
        link_audiencia=notificacion.link_audiencia,
        asignado_a=notificacion.asignado_a,
        estado_gestion="PENDIENTE",
    )

    if notificacion.radicado:
        rad_limpio = notificacion.radicado.replace("'", "").strip()
        proceso_existente = db.query(models.Proceso).filter(models.Proceso.radicado == rad_limpio).first()
        if proceso_existente:
            nueva_notif.proceso_id = proceso_existente.id

    db.add(nueva_notif)
    db.commit()
    db.refresh(nueva_notif)
    return {"mensaje": "Notificación registrada con éxito", "id": nueva_notif.id}


@app.get("/api/notificaciones/pendientes", response_model=List[schemas.NotificacionResponse], dependencies=[ApiAuth])
def listar_notificaciones_pendientes(db: Session = Depends(get_db)):
    return (
        db.query(models.Notificacion)
        .filter(models.Notificacion.estado_gestion == "PENDIENTE")
        .order_by(models.Notificacion.id.desc())
        .all()
    )


@app.patch("/api/notificaciones/{notificacion_id}/completar", dependencies=[ApiAuth])
def marcar_notificacion_gestionada(
    notificacion_id: int = Path(..., description="ID de la notificación"),
    db: Session = Depends(get_db),
):
    notif = db.query(models.Notificacion).filter(models.Notificacion.id == notificacion_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.estado_gestion = "GESTIONADO"
    db.commit()
    return {"mensaje": f"Notificación {notificacion_id} marcada como GESTIONADA"}


@app.post("/api/estados/sincronizar", response_model=dict, dependencies=[ApiAuth])
def registrar_estado_redjudicial(estado: schemas.ActuacionEstadoCreate, db: Session = Depends(get_db)):
    rad = estado.radicado.strip()
    fecha = estado.fecha_notificacion

    # Autos no disponibles: actualizar si ya hay seguimiento abierto (evita duplicados al re-escanear)
    if estado.estado_inyeccion == "AUTO_NO_DISPONIBLE":
        existente = (
            db.query(models.ActuacionEstado)
            .filter(
                models.ActuacionEstado.radicado == rad,
                models.ActuacionEstado.fecha_notificacion == fecha,
                models.ActuacionEstado.estado_inyeccion.in_(
                    ("AUTO_NO_DISPONIBLE", "OMITIDO")
                ),
            )
            .order_by(models.ActuacionEstado.id.desc())
            .first()
        )
        if existente:
            existente.demandante = estado.demandante.strip()
            existente.demandado = estado.demandado.strip()
            existente.descripcion_actuacion = estado.descripcion_actuacion
            existente.etapa_ia = estado.etapa_ia
            existente.actuacion_ia = estado.actuacion_ia
            existente.resumen_ia = estado.resumen_ia
            existente.ruta_pdf_local = None
            existente.pdf_faltante = True
            existente.motivo_falla = estado.motivo_falla or existente.motivo_falla
            db.commit()
            db.refresh(existente)
            return {
                "mensaje": "Seguimiento AUTO_NO_DISPONIBLE actualizado",
                "id": existente.id,
                "actualizado": True,
            }

    nuevo_estado = models.ActuacionEstado(
        fecha_notificacion=fecha,
        radicado=rad,
        demandante=estado.demandante.strip(),
        demandado=estado.demandado.strip(),
        descripcion_actuacion=estado.descripcion_actuacion,
        etapa_ia=estado.etapa_ia,
        actuacion_ia=estado.actuacion_ia,
        resumen_ia=estado.resumen_ia,
        ruta_pdf_local=estado.ruta_pdf_local,
        pdf_faltante=estado.pdf_faltante,
        estado_inyeccion=estado.estado_inyeccion,
        motivo_falla=estado.motivo_falla,
    )

    proceso_existente = (
        db.query(models.Proceso).filter(models.Proceso.radicado == rad).first()
    )
    if proceso_existente:
        nuevo_estado.proceso_id = proceso_existente.id

    db.add(nuevo_estado)
    db.commit()
    db.refresh(nuevo_estado)
    return {"mensaje": "Actuación de RedJudicial registrada", "id": nuevo_estado.id}


@app.get("/api/estados/pendientes", response_model=List[schemas.ActuacionEstadoResponse], dependencies=[ApiAuth])
def listar_estados_pendientes(db: Session = Depends(get_db)):
    return (
        db.query(models.ActuacionEstado)
        .filter(models.ActuacionEstado.estado_inyeccion == "PENDIENTE")
        .order_by(models.ActuacionEstado.id.desc())
        .all()
    )


@app.get(
    "/api/estados/seguimiento-manual",
    response_model=List[schemas.ActuacionEstadoResponse],
    dependencies=[ApiAuth],
)
def listar_estados_seguimiento_manual(db: Session = Depends(get_db)):
    """Autos no disponibles en micrositios u otros que requieren gestión humana."""
    from sqlalchemy import or_, and_

    return (
        db.query(models.ActuacionEstado)
        .filter(
            models.ActuacionEstado.estado_inyeccion != "GESTIONADO",
            or_(
                models.ActuacionEstado.estado_inyeccion.in_(
                    ("AUTO_NO_DISPONIBLE", "OMITIDO")
                ),
                and_(
                    models.ActuacionEstado.estado_inyeccion == "PENDIENTE",
                    models.ActuacionEstado.actuacion_ia.ilike("%AUTO NO DISPONIBLE%"),
                ),
            ),
        )
        .order_by(models.ActuacionEstado.id.desc())
        .all()
    )


@app.patch("/api/estados/{estado_id}/completar-seguimiento", dependencies=[ApiAuth])
def marcar_seguimiento_gestionado(
    estado_id: int = Path(..., description="ID del estado RedJudicial"),
    db: Session = Depends(get_db),
):
    registro = db.query(models.ActuacionEstado).filter(models.ActuacionEstado.id == estado_id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de estado no encontrado")
    registro.estado_inyeccion = "GESTIONADO"
    if not registro.motivo_falla:
        registro.motivo_falla = "Seguimiento manual cerrado desde el tablero"
    db.commit()
    return {"mensaje": f"Estado {estado_id} marcado como GESTIONADO"}


@app.patch("/api/estados/{estado_id}/actualizar", dependencies=[ApiAuth])
def actualizar_estado_inyeccion(
    estado_id: int,
    estado_inyeccion: str,
    motivo_falla: Optional[str] = None,
    db: Session = Depends(get_db),
):
    registro = db.query(models.ActuacionEstado).filter(models.ActuacionEstado.id == estado_id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de estado no encontrado")
    registro.estado_inyeccion = estado_inyeccion
    if motivo_falla:
        registro.motivo_falla = motivo_falla
    db.commit()
    return {"mensaje": f"Estado {estado_id} actualizado a {estado_inyeccion}"}


@app.post("/api/demandas/cargar-excel", dependencies=[ApiAuth])
async def cargar_demandas_desde_excel(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Formato inválido. Debe ser archivo Excel (.xlsx)")

    try:
        contenido = await archivo.read()
        if not contenido:
            raise HTTPException(status_code=400, detail="El archivo Excel está vacío.")

        df = pd.read_excel(io.BytesIO(contenido))
        if df.empty:
            raise HTTPException(status_code=400, detail="La hoja de Excel no contiene filas de datos.")

        faltantes = [col for col in COLUMNAS_EXCEL_REQUERIDAS if col not in df.columns]
        if faltantes:
            raise HTTPException(
                status_code=400,
                detail=f"Columnas faltantes obligatorias: {', '.join(faltantes)}",
            )

        total_creadas = 0
        for _, fila in df.iterrows():
            identificacion = _celda_str(fila, "Identificacion_Demandado")
            if not identificacion:
                continue

            numero_juz = _celda_str(fila, "Numero_Juzgado")
            if not numero_juz:
                numero_juz = "0"

            demanda = models.DemandaNueva(
                tipo_id_demandado=_celda_str(fila, "Tipo_Id_Demandado", "CC") or "CC",
                identificacion_demandado=identificacion,
                nombres_demandado=_celda_str(fila, "Nombres_Demandado"),
                apellidos_demandado=_celda_str(fila, "Apellidos_Demandado"),
                tipo_id_codeudor=_celda_opcional(fila, "Tipo_Id_Codeudor"),
                identificacion_codeudor=_celda_opcional(fila, "Identificacion_Codeudor"),
                nombres_codeudor=_celda_opcional(fila, "Nombres_Codeudor"),
                apellidos_codeudor=_celda_opcional(fila, "Apellidos_Codeudor"),
                cartera_dropdown=_celda_str(fila, "Cartera_Dropdown"),
                nombre_demandante=_celda_str(fila, "Nombre_Demandante"),
                nit_demandante=_celda_str(fila, "NIT_Demandante"),
                fecha_ingreso_cartera=_celda_fecha(fila, "Fecha_Ingreso_Cartera"),
                fecha_presentacion_demanda=_celda_fecha(fila, "Fecha_Presentacion_Demanda"),
                monto_pretension=_celda_float(fila, "Monto_Pretension"),
                tipo_bien_medida=_celda_opcional(fila, "Tipo_Bien_Medida"),
                descripcion_medida=_celda_opcional(fila, "Descripcion_Medida"),
                tipo_intervencion=_celda_str(fila, "Tipo_Intervencion", "ASECOB") or "ASECOB",
                radicacion=_celda_opcional(fila, "Radicacion"),
                referencia=_celda_opcional(fila, "Referencia"),
                clase_proceso=_celda_opcional(fila, "Clase_Proceso"),
                tipo_juzgado=_celda_opcional(fila, "Tipo_Juzgado"),
                numero_juzgado=numero_juz[:4],
                ciudad_juzgado=_celda_opcional(fila, "Ciudad_Juzgado"),
                estado_robot="PENDIENTE",
            )
            db.add(demanda)
            total_creadas += 1

        db.commit()
        return {"mensaje": f"Archivo procesado. Se cargaron {total_creadas} demandas nuevas a la cola."}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error procesando la plantilla: {e}") from e


@app.get("/api/demandas/descargar-plantilla", dependencies=[ApiAuth])
def descargar_plantilla_excel():
    output = io.BytesIO(generar_plantilla_bytes())
    headers = {"Content-Disposition": 'attachment; filename="Plantilla_Radicacion_Inteligente.xlsx"'}
    return StreamingResponse(
        output,
        headers=headers,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/demandas/pendientes", response_model=List[schemas.DemandaNuevaResponse], dependencies=[ApiAuth])
def listar_demandas_pendientes(db: Session = Depends(get_db)):
    return (
        db.query(models.DemandaNueva)
        .filter(models.DemandaNueva.estado_robot == "PENDIENTE")
        .order_by(models.DemandaNueva.id.asc())
        .all()
    )


@app.patch("/api/demandas/{demanda_id}/actualizar", dependencies=[ApiAuth])
def actualizar_estado_demanda(
    demanda_id: int,
    estado_robot: str,
    motivo_error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    demanda = db.query(models.DemandaNueva).filter(models.DemandaNueva.id == demanda_id).first()
    if not demanda:
        raise HTTPException(status_code=404, detail="Demanda no encontrada")
    demanda.estado_robot = estado_robot
    if motivo_error is not None:
        demanda.motivo_error = motivo_error
    db.commit()
    return {"mensaje": f"Demanda {demanda_id} actualizada a {estado_robot}"}


# ==========================================
# REGLAS DE CORREO (Cartero configurable)
# ==========================================
@app.get("/api/reglas-correo", response_model=List[schemas.ReglaCorreoResponse], dependencies=[ApiAuth])
def listar_reglas_correo(
    solo_activas: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(models.ReglaCorreo)
    if solo_activas:
        q = q.filter(models.ReglaCorreo.activo.is_(True))
    return q.order_by(models.ReglaCorreo.prioridad.asc(), models.ReglaCorreo.id.asc()).all()


@app.get(
    "/api/reglas-correo/activas",
    response_model=List[schemas.ReglaCorreoResponse],
    dependencies=[ApiAuth],
)
def listar_reglas_correo_activas(db: Session = Depends(get_db)):
    """Endpoint corto para el Cartero al inicio de cada ciclo."""
    return (
        db.query(models.ReglaCorreo)
        .filter(models.ReglaCorreo.activo.is_(True))
        .order_by(models.ReglaCorreo.prioridad.asc(), models.ReglaCorreo.id.asc())
        .all()
    )


@app.get("/api/reglas-correo/meta", dependencies=[ApiAuth])
def meta_reglas_correo():
    return {
        "tipos_match": list(TIPOS_MATCH),
        "acciones": list(ACCIONES),
        "ayuda": {
            "CORREO": "Coincide con el email exacto del remitente (ej. contabilidad@empresa.com)",
            "DOMINIO": "Coincide con el dominio del From (ej. cendoj.ramajudicial.gov.co)",
            "ASUNTO": "Si el asunto contiene ese texto (sin importar tildes)",
            "IGNORAR": "Marca leído y no reenvía",
            "ALERTA_MANUAL": "Avisa al equipo (o a asignado_a) sin buscar radicado",
            "BUSCAR_RADICADO": "Procesa como providencia: busca radicado y reenvía",
        },
    }


@app.post("/api/reglas-correo", response_model=schemas.ReglaCorreoResponse, dependencies=[ApiAuth])
def crear_regla_correo(regla: schemas.ReglaCorreoCreate, db: Session = Depends(get_db)):
    err = validar_regla(regla.tipo_match, regla.accion, regla.patron)
    if err:
        raise HTTPException(status_code=400, detail=err)
    nueva = models.ReglaCorreo(
        nombre=(regla.nombre or "Regla").strip()[:120],
        tipo_match=regla.tipo_match.strip().upper(),
        patron=regla.patron.strip(),
        accion=regla.accion.strip().upper(),
        asignado_a=(regla.asignado_a or None),
        prioridad=int(regla.prioridad or 100),
        activo=bool(regla.activo),
        notas=regla.notas,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@app.patch("/api/reglas-correo/{regla_id}", response_model=schemas.ReglaCorreoResponse, dependencies=[ApiAuth])
def actualizar_regla_correo(
    regla_id: int,
    cambios: schemas.ReglaCorreoUpdate,
    db: Session = Depends(get_db),
):
    regla = db.query(models.ReglaCorreo).filter(models.ReglaCorreo.id == regla_id).first()
    if not regla:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    data = cambios.model_dump(exclude_unset=True)
    tipo = data.get("tipo_match", regla.tipo_match)
    accion = data.get("accion", regla.accion)
    patron = data.get("patron", regla.patron)
    err = validar_regla(str(tipo), str(accion), str(patron))
    if err:
        raise HTTPException(status_code=400, detail=err)
    for campo, valor in data.items():
        if campo in ("tipo_match", "accion") and isinstance(valor, str):
            valor = valor.strip().upper()
        if campo == "patron" and isinstance(valor, str):
            valor = valor.strip()
        if campo == "nombre" and isinstance(valor, str):
            valor = valor.strip()[:120]
        setattr(regla, campo, valor)
    db.commit()
    db.refresh(regla)
    return regla


@app.delete("/api/reglas-correo/{regla_id}", dependencies=[ApiAuth])
def eliminar_regla_correo(regla_id: int, db: Session = Depends(get_db)):
    regla = db.query(models.ReglaCorreo).filter(models.ReglaCorreo.id == regla_id).first()
    if not regla:
        raise HTTPException(status_code=404, detail="Regla no encontrada")
    db.delete(regla)
    db.commit()
    return {"mensaje": f"Regla {regla_id} eliminada"}


@app.post("/api/reglas-correo/sembrar-defaults", dependencies=[ApiAuth])
def sembrar_reglas_correo_defaults(db: Session = Depends(get_db)):
    """Inserta reglas base solo si la tabla está vacía (primera vez)."""
    existentes = db.query(models.ReglaCorreo).count()
    if existentes > 0:
        return {
            "mensaje": "Ya hay reglas; no se sembraron defaults.",
            "total": existentes,
            "creadas": 0,
        }
    creadas = 0
    for item in REGLAS_DEFAULT:
        db.add(
            models.ReglaCorreo(
                nombre=item["nombre"],
                tipo_match=item["tipo_match"],
                patron=item["patron"],
                accion=item["accion"],
                asignado_a=item.get("asignado_a"),
                prioridad=item.get("prioridad", 100),
                activo=True,
                notas=item.get("notas"),
            )
        )
        creadas += 1
    db.commit()
    return {"mensaje": "Reglas por defecto creadas", "creadas": creadas, "total": creadas}


@app.get("/dashboard", response_class=HTMLResponse)
def ver_dashboard(request: Request, db: Session = Depends(get_db)):
    if DASHBOARD_PASSWORD and not acceso_dashboard_ok(request):
        return RedirectResponse("/entrar", status_code=303)

    pendientes_buzon = (
        db.query(models.Notificacion)
        .filter(models.Notificacion.estado_gestion == "PENDIENTE")
        .order_by(models.Notificacion.id.desc())
        .all()
    )
    estados_vigia = (
        db.query(models.ActuacionEstado)
        .filter(models.ActuacionEstado.estado_inyeccion == "PENDIENTE")
        .order_by(models.ActuacionEstado.id.desc())
        .all()
    )
    from sqlalchemy import or_, and_

    autos_no_disponibles = (
        db.query(models.ActuacionEstado)
        .filter(
            models.ActuacionEstado.estado_inyeccion != "GESTIONADO",
            or_(
                models.ActuacionEstado.estado_inyeccion.in_(
                    ("AUTO_NO_DISPONIBLE", "OMITIDO")
                ),
                and_(
                    models.ActuacionEstado.estado_inyeccion == "PENDIENTE",
                    models.ActuacionEstado.actuacion_ia.ilike("%AUTO NO DISPONIBLE%"),
                ),
            ),
        )
        .order_by(models.ActuacionEstado.id.desc())
        .all()
    )
    demandas_radicar = (
        db.query(models.DemandaNueva)
        .filter(models.DemandaNueva.estado_robot == "PENDIENTE")
        .order_by(models.DemandaNueva.id.desc())
        .all()
    )
    reglas_correo = (
        db.query(models.ReglaCorreo)
        .order_by(models.ReglaCorreo.prioridad.asc(), models.ReglaCorreo.id.asc())
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "notificaciones": pendientes_buzon,
            "estados": estados_vigia,
            "autos_no_disponibles": autos_no_disponibles,
            "demandas": demandas_radicar,
            "reglas_correo": reglas_correo,
        },
    )
