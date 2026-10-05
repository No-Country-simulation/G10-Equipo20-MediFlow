"""Directorio de pacientes (RN-M6): localizar todo lo asociado a una persona. Solo para roles clínicos (RN-K1, RN-K2)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import cuenta_actual, firmante, get_session
from app.models.documento import Documento
from app.models.paciente import Paciente
from app.services.errores import ErrorDeRevision
from app.services.pacientes import ServicioPacientes
from app.services.usuarios import ServicioUsuarios

router = APIRouter(prefix="/pacientes", tags=["pacientes"])


def _ficha(paciente: Paciente, documentos: int) -> dict:
    return {
        "id": paciente.id, "pais": paciente.pais, "tipo_documento": paciente.tipo_documento, "numero_documento": paciente.numero_documento,
        "nombre": paciente.nombre, "edad": paciente.edad, "sexo": paciente.sexo, "documentos": documentos,
        "creado_en": paciente.creado_en.isoformat() if paciente.creado_en else None,
        "actualizado_en": paciente.actualizado_en.isoformat() if paciente.actualizado_en else None,
    }


def _documento(doc: Documento) -> dict:
    resultado = doc.resultado_json or {}
    return {
        "documento_id": doc.documento_id, "version": doc.version, "estado": doc.estado, "nivel_prioridad": doc.nivel_prioridad,
        "tipo": resultado.get("clasificacion", {}).get("tipo"),
        "fecha_documento": resultado.get("extraccion", {}).get("fecha_documento"),
        "creado_en": doc.creado_en.isoformat() if doc.creado_en else None,
    }


@router.get("")
def listar_pacientes(
    q: Annotated[str, Query(max_length=128)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
):
    filas, total = ServicioPacientes(session).listar(q=q, limit=limit, offset=offset)
    return {"items": [_ficha(p, n) for p, n in filas], "total": total, "limit": limit, "offset": offset}


@router.get("/{paciente_id}")
def consultar_paciente(paciente_id: int, session: Session = Depends(get_session)):
    servicio = ServicioPacientes(session)
    paciente = session.get(Paciente, paciente_id)
    if paciente is None:
        raise HTTPException(status_code=404, detail="paciente no encontrado")
    documentos = servicio.documentos(paciente_id)
    return {**_ficha(paciente, servicio.contar_documentos(paciente_id)), "historial": paciente.historial_json or [],
            "documentos_listado": [_documento(d) for d in documentos]}


class EdicionPaciente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usuario: str = Field(..., min_length=1)  # RN-G4
    rol: str = Field(..., min_length=1)
    motivo: str = ""
    nombre: str | None = Field(default=None, max_length=255)
    edad: int | None = Field(default=None, ge=0, le=130)
    sexo: str | None = Field(default=None, max_length=16)


@router.patch("/{paciente_id}")
def editar_paciente(paciente_id: int, cuerpo: EdicionPaciente, session: Session = Depends(get_session), cuenta=Depends(cuenta_actual)):
    """Corrige un dato mal registrado (por ejemplo, un nombre con error que genera conflictos). El número de documento no se edita."""
    quien = firmante(session, cuenta, cuerpo.usuario, cuerpo.rol)
    cambios = cuerpo.model_dump(exclude_unset=True, exclude={"usuario", "rol", "motivo"})
    try:
        if quien.rol != "auditor_clinico":
            raise ErrorDeRevision(403, f"RN-K2: los datos de un paciente los corrige el auditor clínico, no el rol {quien.rol}")
        ServicioUsuarios(session).validar_actor(quien.usuario, "editar_paciente", quien.rol)
        if not cambios:
            raise ErrorDeRevision(422, "no hay nada que cambiar")
        servicio = ServicioPacientes(session)
        paciente = servicio.editar(paciente_id, usuario=quien.usuario, motivo=cuerpo.motivo, cambios=cambios)
    except ErrorDeRevision as error:
        session.rollback()
        raise HTTPException(status_code=error.codigo, detail=error.detalle) from error
    return {**_ficha(paciente, servicio.contar_documentos(paciente.id)), "historial": paciente.historial_json or []}
