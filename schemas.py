from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# ==========================================
# ESQUEMAS: BUZÓN DE NOTIFICACIONES
# ==========================================
class NotificacionCreate(BaseModel):
  radicado: Optional[str] = None
  asunto_original: str
  remitente: str
  clasificacion_ia: str
  sub_embargo: Optional[str] = None
  fecha_audiencia: Optional[str] = None
  link_audiencia: Optional[str] = None
  asignado_a: str


class NotificacionResponse(BaseModel):
  id: int
  fecha_recepcion: datetime
  asunto_original: str
  remitente: str
  clasificacion_ia: str
  sub_embargo: Optional[str] = None
  fecha_audiencia: Optional[str] = None
  link_audiencia: Optional[str] = None
  estado_gestion: str
  asignado_a: Optional[str] = None

  class Config:
    from_attributes = True


# ==========================================
# ESQUEMAS: ESTADOS REDJUDICIAL
# ==========================================
class ActuacionEstadoCreate(BaseModel):
  fecha_notificacion: str
  radicado: str
  demandante: str
  demandado: str
  descripcion_actuacion: str
  etapa_ia: str
  actuacion_ia: str
  resumen_ia: str
  ruta_pdf_local: Optional[str] = None
  pdf_faltante: bool = False
  estado_inyeccion: str = "PENDIENTE"
  motivo_falla: Optional[str] = None


class ActuacionEstadoResponse(BaseModel):
  id: int
  fecha_notificacion: str
  radicado: str
  demandante: str
  demandado: str
  descripcion_actuacion: str
  etapa_ia: str
  actuacion_ia: str
  resumen_ia: str
  ruta_pdf_local: Optional[str] = (
      None  # <-- Campo agregado para que el worker acceda al archivo local
  )
  pdf_faltante: bool
  estado_inyeccion: str
  motivo_falla: Optional[str] = None

  class Config:
    from_attributes = True


# ==========================================
# ESQUEMAS: PLANTILLA DEMANDAS NUEVAS
# ==========================================
class DemandaNuevaCreate(BaseModel):
  tipo_id_demandado: str
  identificacion_demandado: str
  nombres_demandado: str
  apellidos_demandado: str
  tipo_id_codeudor: Optional[str] = None
  identificacion_codeudor: Optional[str] = None
  nombres_codeudor: Optional[str] = None
  apellidos_codeudor: Optional[str] = None
  cartera_dropdown: str
  nombre_demandante: str
  nit_demandante: str
  fecha_ingreso_cartera: Optional[datetime] = None
  fecha_presentacion_demanda: Optional[datetime] = None
  monto_pretension: float = 0.0
  tipo_bien_medida: Optional[str] = None
  descripcion_medida: Optional[str] = None
  tipo_intervencion: Optional[str] = "ASECOB"


class DemandaNuevaResponse(DemandaNuevaCreate):
  id: int
  estado_robot: str
  fecha_creacion: datetime

  class Config:
    from_attributes = True