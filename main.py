import io
import datetime
from typing import List, Optional
import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, Path, UploadFile, File, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

from dotenv import load_dotenv

import io
import datetime
from typing import List, Optional
import pandas as pd
from fastapi import FastAPI, Depends, HTTPException, Path, UploadFile, File, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

import models
import schemas
from database import engine, SessionLocal

load_dotenv()

# Conexión al cuaderno en la nube
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("❌ ERROR: La variable DATABASE_URL no fue encontrada. Revisa tu archivo .env")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Inicialización física de tablas en Supabase
models.Base.metadata.create_all(bind=engine)

# ¡ESTA ES LA LÍNEA QUE FALTABA! Creación de la app
app = FastAPI(
    title="Torre de Control - LegalTech Asecob S.A.S.",
    description="Backend centralizado para correo CENDOJ, estados de RedJudicial y radicación en Redelex.",
    version="2.0.0"
)

templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# RUTAS DE ESTADO Y MÉTRICAS
# ==========================================
@app.get("/")
def leer_estado_servidor():
    return {"estado": "En línea", "sistema": "Dependiente Judicial Virtual Activo"}

@app.get("/api/estadisticas")
def obtener_estadisticas_basicas(db: Session = Depends(get_db)):
    total_notif = db.query(models.Notificacion).count()
    total_estados = db.query(models.ActuacionEstado).count()
    total_demandas = db.query(models.DemandaNueva).count()
    return {
        "notificaciones_correo": total_notif,
        "estados_redjudicial": total_estados,
        "demandas_para_radicar": total_demandas
    }

# ==========================================
# MÓDULO 1: BUZÓN DE NOTIFICACIONES (GMAIL)
# ==========================================
@app.post("/api/notificaciones/", response_model=dict)
def recibir_notificacion_robot(notificacion: schemas.NotificacionCreate, db: Session = Depends(get_db)):
    nueva_notif = models.Notificacion(
        asunto_original=notificacion.asunto_original,
        remitente=notificacion.remitente,
        clasificacion_ia=notificacion.clasificacion_ia,
        sub_embargo=notificacion.sub_embargo,
        fecha_audiencia=notificacion.fecha_audiencia,
        link_audiencia=notificacion.link_audiencia,
        asignado_a=notificacion.asignado_a,
        estado_gestion="PENDIENTE"
    )
    
    # Enlace relacional si el radicado ya existe en la base
    if notificacion.radicado:
        rad_limpio = notificacion.radicado.replace("'", "").strip()
        proceso_existente = db.query(models.Proceso).filter(models.Proceso.radicado == rad_limpio).first()
        if proceso_existente:
            nueva_notif.proceso_id = proceso_existente.id
            
    db.add(nueva_notif)
    db.commit()
    db.refresh(nueva_notif)
    return {"mensaje": "Notificación registrada con éxito", "id": nueva_notif.id}

@app.get("/api/notificaciones/pendientes", response_model=List[schemas.NotificacionResponse])
def listar_notificaciones_pendientes(db: Session = Depends(get_db)):
    return db.query(models.Notificacion).filter(
        models.Notificacion.estado_gestion == "PENDIENTE"
    ).order_by(models.Notificacion.id.desc()).all()

@app.patch("/api/notificaciones/{notificacion_id}/completar")
def marcar_notificacion_gestionada(
    notificacion_id: int = Path(..., description="ID de la notificación"),
    db: Session = Depends(get_db)
):
    notif = db.query(models.Notificacion).filter(models.Notificacion.id == notificacion_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.estado_gestion = "GESTIONADO"
    db.commit()
    return {"mensaje": f"Notificación {notificacion_id} marcada como GESTIONADA"}

# ==========================================
# MÓDULO 2: VIGILANCIA REDJUDICIAL
# ==========================================
@app.post("/api/estados/sincronizar", response_model=dict)
def registrar_estado_redjudicial(estado: schemas.ActuacionEstadoCreate, db: Session = Depends(get_db)):
    nuevo_estado = models.ActuacionEstado(
        fecha_notificacion=estado.fecha_notificacion,
        radicado=estado.radicado.strip(),
        demandante=estado.demandante.strip(),
        demandado=estado.demandado.strip(),
        descripcion_actuacion=estado.descripcion_actuacion,
        etapa_ia=estado.etapa_ia,
        actuacion_ia=estado.actuacion_ia,
        resumen_ia=estado.resumen_ia,
        ruta_pdf_local=estado.ruta_pdf_local,
        pdf_faltante=estado.pdf_faltante,
        estado_inyeccion=estado.estado_inyeccion,
        motivo_falla=estado.motivo_falla
    )
    
    # Enlace automático por radicado
    proceso_existente = db.query(models.Proceso).filter(models.Proceso.radicado == estado.radicado.strip()).first()
    if proceso_existente:
        nuevo_estado.proceso_id = proceso_existente.id
        
    db.add(nuevo_estado)
    db.commit()
    db.refresh(nuevo_estado)
    return {"mensaje": "Actuación de RedJudicial registrada", "id": nuevo_estado.id}

@app.get("/api/estados/pendientes", response_model=List[schemas.ActuacionEstadoResponse])
def listar_estados_pendientes(db: Session = Depends(get_db)):
    return db.query(models.ActuacionEstado).filter(
        models.ActuacionEstado.estado_inyeccion == "PENDIENTE"
    ).order_by(models.ActuacionEstado.id.desc()).all()

@app.patch("/api/estados/{estado_id}/actualizar")
def actualizar_estado_inyeccion(
    estado_id: int,
    estado_inyeccion: str,
    motivo_falla: Optional[str] = None,
    db: Session = Depends(get_db)
):
    registro = db.query(models.ActuacionEstado).filter(models.ActuacionEstado.id == estado_id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro de estado no encontrado")
    registro.estado_inyeccion = estado_inyeccion
    if motivo_falla:
        registro.motivo_falla = motivo_falla
    db.commit()
    return {"mensaje": f"Estado {estado_id} actualizado a {estado_inyeccion}"}

# ==========================================
# MÓDULO 3: PLANTILLA DE RADICACIÓN
# ==========================================
@app.post("/api/demandas/cargar-excel")
async def cargar_demandas_desde_excel(archivo: UploadFile = File(...), db: Session = Depends(get_db)):
    if not archivo.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Formato inválido. Debe ser archivo Excel (.xlsx)")
    
    try:
        contenido = await archivo.read()
        df = pd.read_excel(io.BytesIO(contenido))
        
        columnas_requeridas = ['Tipo_Id_Demandado', 'Identificacion_Demandado', 'Nombres_Demandado', 'Apellidos_Demandado', 'Cartera_Dropdown']
        for col in columnas_requeridas:
            if col not in df.columns:
                raise HTTPException(status_code=400, detail=f"Columna faltante obligatoria: {col}")
        
        total_creadas = 0
        for _, fila in df.iterrows():
            if pd.isna(fila.get('Identificacion_Demandado')):
                continue
            
            demanda = models.DemandaNueva(
                tipo_id_demandado=str(fila.get('Tipo_Id_Demandado', 'CC')),
                identificacion_demandado=str(fila.get('Identificacion_Demandado')).split('.')[0].strip(),
                nombres_demandado=str(fila.get('Nombres_Demandado', '')),
                apellidos_demandado=str(fila.get('Apellidos_Demandado', '')),
                tipo_id_codeudor=str(fila.get('Tipo_Id_Codeudor')) if not pd.isna(fila.get('Tipo_Id_Codeudor')) else None,
                identificacion_codeudor=str(fila.get('Identificacion_Codeudor')).split('.')[0].strip() if not pd.isna(fila.get('Identificacion_Codeudor')) else None,
                nombres_codeudor=str(fila.get('Nombres_Codeudor')) if not pd.isna(fila.get('Nombres_Codeudor')) else None,
                apellidos_codeudor=str(fila.get('Apellidos_Codeudor')) if not pd.isna(fila.get('Apellidos_Codeudor')) else None,
                cartera_dropdown=str(fila.get('Cartera_Dropdown', '')),
                nombre_demandante=str(fila.get('Nombre_Demandante', '')),
                nit_demandante=str(fila.get('NIT_Demandante', '')).split('.')[0].strip(),
                fecha_ingreso_cartera=pd.to_datetime(fila.get('Fecha_Ingreso_Cartera'), errors='coerce'),
                fecha_presentacion_demanda=pd.to_datetime(fila.get('Fecha_Presentacion_Demanda'), errors='coerce'),
                monto_pretension=float(fila.get('Monto_Pretension', 0.0)) if not pd.isna(fila.get('Monto_Pretension')) else 0.0,
                tipo_bien_medida=str(fila.get('Tipo_Bien_Medida', '')) if not pd.isna(fila.get('Tipo_Bien_Medida')) else None,
                descripcion_medida=str(fila.get('Descripcion_Medida', '')) if not pd.isna(fila.get('Descripcion_Medida')) else None,
                tipo_intervencion=str(fila.get('Tipo_Intervencion', 'ASECOB')),
                estado_robot="PENDIENTE"
            )
            db.add(demanda)
            total_creadas += 1
            
        db.commit()
        return {"mensaje": f"Archivo procesado. Se cargaron {total_creadas} demandas nuevas a la cola."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error procesando la plantilla: {str(e)}")

@app.get("/api/demandas/descargar-plantilla")
def descargar_plantilla_excel():
    columnas = [
        'Tipo_Id_Demandado', 'Identificacion_Demandado', 'Nombres_Demandado', 'Apellidos_Demandado',
        'Tipo_Id_Codeudor', 'Identificacion_Codeudor', 'Nombres_Codeudor', 'Apellidos_Codeudor',
        'Cartera_Dropdown', 'Nombre_Demandante', 'NIT_Demandante',
        'Fecha_Ingreso_Cartera', 'Fecha_Presentacion_Demanda', 'Monto_Pretension',
        'Tipo_Bien_Medida', 'Descripcion_Medida', 'Tipo_Intervencion', 'Estado_Robot'
    ]
    df_vacio = pd.DataFrame(columns=columnas)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_vacio.to_excel(writer, index=False, sheet_name='Sheet1')
    output.seek(0)
    
    headers = {'Content-Disposition': 'attachment; filename="Plantilla_Radicacion_Inteligente.xlsx"'}
    return StreamingResponse(output, headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.get("/api/demandas/pendientes", response_model=List[schemas.DemandaNuevaResponse])
def listar_demandas_pendientes(db: Session = Depends(get_db)):
    return db.query(models.DemandaNueva).filter(
        models.DemandaNueva.estado_robot == "PENDIENTE"
    ).order_by(models.DemandaNueva.id.asc()).all()

@app.patch("/api/demandas/{demanda_id}/actualizar")
def actualizar_estado_demanda(
    demanda_id: int,
    estado_robot: str,
    motivo_error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    demanda = db.query(models.DemandaNueva).filter(models.DemandaNueva.id == demanda_id).first()
    if not demanda:
        raise HTTPException(status_code=404, detail="Demanda no encontrada")
    demanda.estado_robot = estado_robot
    db.commit()
    return {"mensaje": f"Demanda {demanda_id} actualizada a {estado_robot}"}

# ==========================================
# MESA DE CONTROL (FRONTEND JINJA2)
# ==========================================
@app.get("/dashboard", response_class=HTMLResponse)
def ver_dashboard(request: Request, db: Session = Depends(get_db)):
    pendientes_buzon = db.query(models.Notificacion).filter(
        models.Notificacion.estado_gestion == "PENDIENTE"
    ).order_by(models.Notificacion.id.desc()).all()
    
    estados_vigia = db.query(models.ActuacionEstado).filter(
        models.ActuacionEstado.estado_inyeccion == "PENDIENTE"
    ).order_by(models.ActuacionEstado.id.desc()).all()
    
    demandas_radicar = db.query(models.DemandaNueva).filter(
        models.DemandaNueva.estado_robot == "PENDIENTE"
    ).order_by(models.DemandaNueva.id.desc()).all()
    
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "notificaciones": pendientes_buzon,
            "estados": estados_vigia,
            "demandas": demandas_radicar
        }
    )