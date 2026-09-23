import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Text
from sqlalchemy.orm import relationship
from database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, index=True)
    correo = Column(String, unique=True, index=True)
    rol = Column(String, default="ABOGADO")  # ADMIN, ABOGADO, COORDINADOR, ROBOT
    activo = Column(Boolean, default=True)

class Cartera(Base):
    __tablename__ = "carteras"

    id = Column(Integer, primary_key=True, index=True)
    nombre_cliente = Column(String, unique=True, index=True)  # Ej: SUZUKI, REENCAFE SAS
    correo_asignado = Column(String)                          # Ej: juridico@asecobsas.com
    activo = Column(Boolean, default=True)

    procesos = relationship("Proceso", back_populates="cartera")

class Proceso(Base):
    __tablename__ = "procesos"

    id = Column(Integer, primary_key=True, index=True)
    radicado = Column(String(23), unique=True, index=True)
    demandante = Column(String, index=True)
    demandado = Column(String, index=True)
    id_redelex = Column(String, index=True, nullable=True)     # ID interno para inyección en Redelex
    cartera_id = Column(Integer, ForeignKey("carteras.id"), nullable=True)

    cartera = relationship("Cartera", back_populates="procesos")
    notificaciones = relationship("Notificacion", back_populates="proceso")
    actuaciones_estados = relationship("ActuacionEstado", back_populates="proceso")

class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(Integer, primary_key=True, index=True)
    fecha_recepcion = Column(DateTime, default=datetime.datetime.utcnow)
    asunto_original = Column(String)
    remitente = Column(String)
    
    # Análisis cognitivo IA (Gemini / Groq)
    clasificacion_ia = Column(String, index=True)              # TUTELA, DESACATO, OFICIO_MEDIDA_CAUTELAR, FIJACION_AUDIENCIA, OTRO
    sub_embargo = Column(String, nullable=True)                # BANCOS, VEHICULO, INMUEBLE, etc.
    fecha_audiencia = Column(String, nullable=True)
    link_audiencia = Column(String, nullable=True)
    
    # Control operativo
    estado_gestion = Column(String, default="PENDIENTE", index=True)  # PENDIENTE, GESTIONADO, REVISION_MANUAL
    asignado_a = Column(String, nullable=True)
    
    # Enlace relacional
    proceso_id = Column(Integer, ForeignKey("procesos.id"), nullable=True)
    proceso = relationship("Proceso", back_populates="notificaciones")

class ActuacionEstado(Base):
    __tablename__ = "actuaciones_estados"

    id = Column(Integer, primary_key=True, index=True)
    fecha_notificacion = Column(String, index=True)            # Fecha del estado (YYYY-MM-DD)
    radicado = Column(String(23), index=True)
    demandante = Column(String)
    demandado = Column(String)
    descripcion_actuacion = Column(Text)                       # Texto publicado en RedJudicial
    juzgado = Column(String(200), nullable=True)               # Despacho / juzgado RJ
    ciudad_juzgado = Column(String(150), nullable=True)        # Ciudad del despacho RJ
    
    # Clasificación con Catálogo Redelex
    etapa_ia = Column(String)                                  # Ej: 04. MANDAMIENTO DE PAGO, 08. SENTENCIA
    actuacion_ia = Column(String)                              # Ej: MANDAMIENTO DE PAGO Y DECRETO DE MEDIDAS
    resumen_ia = Column(Text)
    
    # Archivos y estado de inyección
    ruta_pdf_local = Column(String, nullable=True)
    pdf_faltante = Column(Boolean, default=False)
    estado_inyeccion = Column(String, default="PENDIENTE", index=True)  # PENDIENTE, EXITOSO, FALLIDO
    motivo_falla = Column(String, nullable=True)
    
    proceso_id = Column(Integer, ForeignKey("procesos.id"), nullable=True)
    proceso = relationship("Proceso", back_populates="actuaciones_estados")

class DemandaNueva(Base):
    __tablename__ = "demandas_nuevas"

    id = Column(Integer, primary_key=True, index=True)
    
    # Sujeto pasivo (Demandado principal)
    tipo_id_demandado = Column(String(10))
    identificacion_demandado = Column(String(30), index=True)
    nombres_demandado = Column(String(100))
    apellidos_demandado = Column(String(100))
    
    # Codeudor / Garante
    tipo_id_codeudor = Column(String(10), nullable=True)
    identificacion_codeudor = Column(String(30), nullable=True)
    nombres_codeudor = Column(String(100), nullable=True)
    apellidos_codeudor = Column(String(100), nullable=True)
    
    # Cartera / Sujeto activo
    cartera_dropdown = Column(String(100), index=True)
    nombre_demandante = Column(String(150))
    nit_demandante = Column(String(30))
    
    # Fechas y cuantía
    fecha_ingreso_cartera = Column(DateTime, nullable=True)
    fecha_presentacion_demanda = Column(DateTime, nullable=True)
    monto_pretension = Column(Float, default=0.0)
    
    # Medida cautelar solicitada
    tipo_bien_medida = Column(String(100), nullable=True)
    descripcion_medida = Column(Text, nullable=True)
    tipo_intervencion = Column(String(50), default="ASECOB")

    # Redelex nuevo.asp (radicación / despacho)
    radicacion = Column(String(50), nullable=True)           # vacío → checkbox sin_numero
    referencia = Column(Text, nullable=True)
    clase_proceso = Column(String(100), nullable=True)
    tipo_juzgado = Column(String(150), nullable=True)        # etiqueta Despacho
    numero_juzgado = Column(String(4), nullable=True)        # default "0"
    ciudad_juzgado = Column(String(150), nullable=True)      # etiqueta o value Redelex
    
    # Control operativo del bot de radicación
    estado_robot = Column(String(50), default="PENDIENTE", index=True)  # PENDIENTE, RADICADO, ERROR
    motivo_error = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.datetime.utcnow)


class ReglaCorreo(Base):
    """
    Reglas operativas del Cartero (editables desde el Dashboard).
    El robot las descarga al iniciar cada ciclo.
    """
    __tablename__ = "reglas_correo"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=False, default="Regla")
    # CORREO | DOMINIO | ASUNTO
    tipo_match = Column(String(20), nullable=False, index=True)
    # email completo, dominio (@ejemplo.com o ejemplo.com) o texto de asunto
    patron = Column(String(300), nullable=False)
    # IGNORAR | ALERTA_MANUAL | BUSCAR_RADICADO
    accion = Column(String(30), nullable=False, index=True)
    # Destino opcional (ALERTA_MANUAL / BUSCAR_RADICADO): email o "TODOS"
    asignado_a = Column(String(200), nullable=True)
    prioridad = Column(Integer, default=100, index=True)  # menor = se evalúa antes
    activo = Column(Boolean, default=True, index=True)
    notas = Column(Text, nullable=True)
    fecha_creacion = Column(DateTime, default=datetime.datetime.utcnow)
    fecha_actualizacion = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
