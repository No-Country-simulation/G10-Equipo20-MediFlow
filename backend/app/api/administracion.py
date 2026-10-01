"""Administración: usuarios (RN-K4, RN-K5), accesos (RN-K3), ficha del pack y puesta en marcha (RN-S3).
Nada clínico pasa por aquí (RN-K2)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, firmante, get_session
from app.core.config import get_settings
from app.core.sesiones import cerrar_sesiones_de, hash_clave
from app.models.alerta import Alerta
from app.models.gobierno import Usuario
from app.services.configuracion import ServicioConfiguracion
from app.services.errores import ErrorDeRevision
from app.services.usuarios import ROLES, TIPOS, ServicioUsuarios

router = APIRouter(prefix="/administracion", tags=["administracion"])


class UsuarioRequest(BaseModel):
    usuario: str = Field(..., min_length=1, max_length=128)
    nombre: str = Field(..., min_length=1, max_length=256)
    rol: str
    tipo: str = "persona"
    actor: str = Field(..., min_length=1)
    clave: str | None = Field(default=None, min_length=8, max_length=128)  # sin clave la cuenta no inicia sesión


class ActorRequest(BaseModel):
    actor: str = Field(..., min_length=1)


class ClaveRequest(ActorRequest):
    clave: str = Field(..., min_length=8, max_length=128)


def _usuario(u: Usuario) -> dict:
    return {
        "usuario": u.usuario, "nombre": u.nombre, "rol": u.rol, "tipo": u.tipo, "activo": u.activo,
        "creado_por": u.creado_por, "creado_en": u.creado_en.isoformat() if u.creado_en else None,
        "desactivado_en": u.desactivado_en.isoformat() if u.desactivado_en else None,
        "con_clave": bool(u.clave_hash),  # nunca el hash
    }


def _administrador(session: Session, actor: str, cuenta) -> str:
    quien = firmante(session, cuenta, actor)
    try:
        ServicioUsuarios(session).validar_actor(quien.usuario, "administrar")
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return quien.usuario


@router.get("/usuarios")
def listar_usuarios(session: Session = Depends(get_session)):
    return [_usuario(u) for u in ServicioUsuarios(session).listar()]


@router.get("/roles")
def roles():
    return {"roles": list(ROLES), "tipos": list(TIPOS)}


@router.post("/usuarios", status_code=201)
def crear_usuario(cuerpo: UsuarioRequest, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    actor = _administrador(session, cuerpo.actor, cuenta)
    try:
        u = ServicioUsuarios(session).crear(usuario=cuerpo.usuario, nombre=cuerpo.nombre, rol=cuerpo.rol, tipo=cuerpo.tipo, actor=actor)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    if cuerpo.clave:
        u.clave_hash = hash_clave(cuerpo.clave)
        session.commit()
    return _usuario(u)


@router.post("/usuarios/{usuario}/clave")
def definir_clave(usuario: str, cuerpo: ClaveRequest, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    """Define o cambia la clave de una cuenta. Sus sesiones abiertas se cierran."""
    _administrador(session, cuerpo.actor, cuenta)
    u = ServicioUsuarios(session).buscar(usuario)
    if u is None:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    u.clave_hash = hash_clave(cuerpo.clave)
    cerrar_sesiones_de(u, session)
    session.commit()
    return _usuario(u)


@router.post("/usuarios/{usuario}/desactivar")
def desactivar(usuario: str, cuerpo: ActorRequest, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    _administrador(session, cuerpo.actor, cuenta)
    try:
        u = ServicioUsuarios(session).cambiar_estado(usuario, activo=False)
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    cerrar_sesiones_de(u, session)  # RN-K4: efecto inmediato también sobre lo que tenga abierto
    session.commit()
    return _usuario(u)


@router.post("/usuarios/{usuario}/activar")
def activar(usuario: str, cuerpo: ActorRequest, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    _administrador(session, cuerpo.actor, cuenta)
    try:
        return _usuario(ServicioUsuarios(session).cambiar_estado(usuario, activo=True))
    except ErrorDeRevision as error:
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error


@router.get("/accesos")
def accesos(documento_id: str | None = None, limit: int = Query(default=200, ge=1, le=1000), session: Session = Depends(get_session)):
    """RN-K3: quién, cuándo y qué vio. Solo IDs de documento (RN-M4)."""
    return [{"documento_id": a.documento_id, "usuario": a.usuario, "accion": a.accion, "fecha_hora": a.fecha_hora.isoformat()}
            for a in ServicioUsuarios(session).accesos(documento_id, limit)]


@router.get("/pack")
def pack(session: Session = Depends(get_session)):
    """Ficha del pack de país activo (sección 4.3). Sin datos clínicos."""
    p = ServicioConfiguracion(session).pack(get_settings().pais_instalacion)
    por_confirmar = []
    for nombre, tipo in p.identidad_paciente.tipos.items():
        if tipo.estado == "por_confirmar":
            por_confirmar.append(f"identidad_paciente.tipos.{nombre}")
    for h in p.hallazgos_criticos:
        if h.estado == "por_confirmar":
            por_confirmar.append(f"hallazgos_criticos.{h.concepto}")
    for nombre, cobertura in p.coberturas.items():
        if cobertura.estado == "por_confirmar":
            por_confirmar.append(f"coberturas.{nombre}")
    for nombre, programa in p.programas_cobertura.items():
        if programa.estado == "por_confirmar":
            por_confirmar.append(f"programas_cobertura.{nombre}")
    if p.terminologia.procedimientos_estado == "por_confirmar":
        por_confirmar.append("terminologia.procedimientos")
    if p.medicamentos.control_especial_estado == "por_confirmar":
        por_confirmar.append("medicamentos.control_especial")
    return {
        "pais": p.pais,
        "nombre": p.nombre,
        "version_pack": p.version_pack,
        "formato": p.formato.model_dump(),
        "terminologia": p.terminologia.model_dump(),
        "identidad_profesional": {"registro": p.identidad_profesional.registro, "ambito": p.identidad_profesional.ambito,
                                  "verificacion_en_linea": p.identidad_profesional.verificacion_en_linea.model_dump()},
        "tipos_documento_paciente": {k: {"nombre": v.nombre, "estado": v.estado, "nacional": v.nacional, "no_identificado": v.no_identificado}
                                     for k, v in p.identidad_paciente.tipos.items()},
        "coberturas": {k: v.model_dump() for k, v in p.coberturas.items()},
        "urgencias": p.urgencias.model_dump(),
        "retencion": p.retencion.model_dump(),
        "datos_personales": p.datos_personales.model_dump(),
        "listas": {"hallazgos_criticos": len(p.hallazgos_criticos), "alto_riesgo": len(p.medicamentos.alto_riesgo),
                   "control_especial": len(p.medicamentos.control_especial)},
        "por_confirmar": por_confirmar,
    }


@router.get("/puesta_en_marcha")
def puesta_en_marcha(session: Session = Depends(get_session)):
    """RN-S3: requisitos mínimos para activar la instalación."""
    settings = get_settings()
    usuarios = ServicioUsuarios(session)
    p = ServicioConfiguracion(session).pack(settings.pais_instalacion)
    alerta_acusada = session.scalars(select(Alerta).where(Alerta.estado_acuse == "acusado")).first() is not None
    requisitos = [
        {"clave": "pais", "requisito": "País de la instalación con pack activo", "cumplido": bool(p.pais), "detalle": f"{p.pais} · pack {p.version_pack}"},
        {"clave": "base_legal", "requisito": "Base legal de tratamiento declarada (RN-M8)", "cumplido": bool(settings.base_legal_tratamiento),
         "detalle": settings.base_legal_tratamiento or "pendiente: BASE_LEGAL_TRATAMIENTO en .env"},
        {"clave": "contrato_transmision", "requisito": "Contrato de transmisión internacional (RN-CO19)", "cumplido": settings.contrato_transmision_internacional,
         "detalle": "firmado" if settings.contrato_transmision_internacional else "pendiente: CONTRATO_TRANSMISION_INTERNACIONAL=true en .env"},
        {"clave": "destinos_activos", "requisito": "Destinos de enrutamiento activos", "cumplido": True,
         "detalle": "todos" if not p.destinos_inactivos else f"desactivados por el gestor: {', '.join(p.destinos_inactivos)}"},
        {"clave": "auditor_clinico", "requisito": "Al menos un auditor clínico activo", "cumplido": usuarios.activos_con_rol("auditor_clinico") > 0,
         "detalle": f"{usuarios.activos_con_rol('auditor_clinico')} activos"},
        {"clave": "jefe_urgencias", "requisito": "Al menos un jefe de urgencias activo", "cumplido": usuarios.activos_con_rol("jefe_urgencias") > 0,
         "detalle": f"{usuarios.activos_con_rol('jefe_urgencias')} activos"},
        {"clave": "alerta_prueba_con_acuse", "requisito": "Una alerta de prueba enviada y con acuse", "cumplido": alerta_acusada,
         "detalle": "hay al menos una alerta acusada" if alerta_acusada else "ninguna alerta acusada todavía"},
        {"clave": "sesion_obligatoria", "requisito": "Inicio de sesión obligatorio (RN-K5)", "cumplido": settings.exigir_sesion,
         "detalle": "nada se consulta ni se firma sin sesión" if settings.exigir_sesion else "pendiente: EXIGIR_SESION=true en .env"},
    ]
    return {"listo": all(r["cumplido"] for r in requisitos), "requisitos": requisitos}
