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
  radicacion: Optional[str] = None
  referencia: Optional[str] = None
  clase_proceso: Optional[str] = None
  tipo_juzgado: Optional[str] = None
  numero_juzgado: Optional[str] = None
  ciudad_juzgado: Optional[str] = None


class DemandaNuevaResponse(DemandaNuevaCreate):
  id: int
  estado_robot: str
  motivo_error: Optional[str] = None
  fecha_creacion: datetime

  class Config:
    from_attributes = True


# ==========================================
# ESQUEMAS: REGLAS DE CORREO (Cartero)
# ==========================================
class ReglaCorreoCreate(BaseModel):
  nombre: str = "Regla"
  tipo_match: str  # CORREO | DOMINIO | ASUNTO
  patron: str
  accion: str  # IGNORAR | ALERTA_MANUAL | BUSCAR_RADICADO
  asignado_a: Optional[str] = None
  prioridad: int = 100
  activo: bool = True
  notas: Optional[str] = None


class ReglaCorreoUpdate(BaseModel):
  nombre: Optional[str] = None
  tipo_match: Optional[str] = None
  patron: Optional[str] = None
  accion: Optional[str] = None
  asignado_a: Optional[str] = None
  prioridad: Optional[int] = None
  activo: Optional[bool] = None
  notas: Optional[str] = None


class ReglaCorreoResponse(BaseModel):
  id: int
  nombre: str
  tipo_match: str
  patron: str
  accion: str
  asignado_a: Optional[str] = None
  prioridad: int
  activo: bool
  notas: Optional[str] = None
  fecha_creacion: datetime
  fecha_actualizacion: Optional[datetime] = None

  class Config:
    from_attributes = True
