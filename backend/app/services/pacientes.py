"""Vínculo entre documentos y pacientes (RN-M6, RN-N5) y conflicto de identidad (RN-A4).

El formato de un documento de identidad no prueba la identidad: si el mismo número ya está
registrado con otro nombre, el documento no se vincula solo y una persona lo revisa.
"""
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documento import Documento
from app.models.paciente import Paciente
from app.schemas.resultado import EstadoIdentidad, Paciente as DatosPaciente
from app.services.errores import ErrorDeRevision

_IDENTIDAD_UTIL = (EstadoIdentidad.VALIDO_FORMATO, EstadoIdentidad.VALIDO_VERIFICADO)


def _palabras(nombre: str) -> set[str]:
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", nombre) if unicodedata.category(c) != "Mn")
    return {p for p in sin_tildes.casefold().replace(",", " ").split() if p}


def nombres_compatibles(a: str, b: str) -> bool:
    """El mismo nombre escrito con más o menos nombres y apellidos: uno contiene al otro y comparten al menos dos palabras."""
    pa, pb = _palabras(a), _palabras(b)
    comunes = pa & pb
    return len(comunes) >= min(2, len(pa), len(pb)) and (pa <= pb or pb <= pa)


def identidad_vinculable(datos: DatosPaciente) -> bool:
    """Solo se vincula con documento de formato válido y nombre. Un no identificado (RN-N3) espera a la conciliación."""
    return bool(datos.documento.estado in _IDENTIDAD_UTIL and datos.documento.valor and datos.nombre and datos.nombre.strip())


class ServicioPacientes:
    def __init__(self, session: Session):
        self.session = session

    def buscar(self, pais: str, tipo: str, numero: str) -> Paciente | None:
        return self.session.scalars(select(Paciente).where(
            Paciente.pais == pais, Paciente.tipo_documento == tipo, Paciente.numero_documento == numero)).first()

    def en_conflicto(self, pais: str, datos: DatosPaciente) -> Paciente | None:
        """El paciente ya registrado con ese documento cuando su nombre no es compatible con el del documento clínico."""
        if not identidad_vinculable(datos):
            return None
        existente = self.buscar(pais, datos.documento.tipo.value, datos.documento.valor)
        if existente is not None and not nombres_compatibles(existente.nombre, datos.nombre):
            return existente
        return None

    def vincular(self, documento: Documento, datos: DatosPaciente) -> Paciente | None:
        """Vincula el documento a su paciente y lo crea si es nuevo. Sin identidad útil o con conflicto, no vincula."""
        if not identidad_vinculable(datos) or self.en_conflicto(documento.pais_origen, datos) is not None:
            documento.paciente_id = None
            return None
        paciente = self.buscar(documento.pais_origen, datos.documento.tipo.value, datos.documento.valor)
        if paciente is None:
            paciente = Paciente(pais=documento.pais_origen, tipo_documento=datos.documento.tipo.value, numero_documento=datos.documento.valor,
                                nombre=datos.nombre.strip(), edad=datos.edad, sexo=datos.sexo, historial_json=[])
            self.session.add(paciente)
            self.session.flush()
        else:
            if datos.edad is not None:
                paciente.edad = datos.edad
            if datos.sexo and not paciente.sexo:
                paciente.sexo = datos.sexo
            paciente.actualizado_en = datetime.now(timezone.utc)
        documento.paciente_id = paciente.id
        return paciente

    # --- consulta y edición (RN-M6, RN-G4) ---------------------------------------------------------

    def listar(self, *, q: str = "", limit: int = 20, offset: int = 0) -> tuple[list[tuple[Paciente, int]], int]:
        consulta = select(Paciente)
        if q.strip():
            patron = f"%{q.strip()}%"
            consulta = consulta.where(Paciente.nombre.ilike(patron) | Paciente.numero_documento.ilike(patron))
        total = self.session.scalar(select(func.count()).select_from(consulta.subquery())) or 0
        pacientes = list(self.session.scalars(consulta.order_by(Paciente.actualizado_en.desc(), Paciente.id.desc()).limit(limit).offset(offset)))
        return [(p, self.contar_documentos(p.id)) for p in pacientes], total

    def contar_documentos(self, paciente_id: int) -> int:
        return self.session.scalar(select(func.count(func.distinct(Documento.documento_id))).where(Documento.paciente_id == paciente_id)) or 0

    def documentos(self, paciente_id: int) -> list[Documento]:
        return list(self.session.scalars(select(Documento).where(Documento.paciente_id == paciente_id)
                                         .order_by(Documento.creado_en.desc(), Documento.id.desc())))

    def editar(self, paciente_id: int, *, usuario: str, motivo: str, cambios: dict) -> Paciente:
        paciente = self.session.get(Paciente, paciente_id)
        if paciente is None:
            raise ErrorDeRevision(404, "paciente no encontrado")
        if not motivo.strip():
            raise ErrorDeRevision(422, "RN-G4: editar los datos de un paciente exige motivo")
        if "nombre" in cambios and not (cambios["nombre"] or "").strip():
            raise ErrorDeRevision(422, "el nombre no puede quedar vacío")
        anterior = {campo: getattr(paciente, campo) for campo in cambios}
        for campo, valor in cambios.items():
            setattr(paciente, campo, valor.strip() if isinstance(valor, str) else valor)
        nuevo = {campo: getattr(paciente, campo) for campo in cambios}
        if nuevo == anterior:
            return paciente
        paciente.actualizado_en = datetime.now(timezone.utc)
        paciente.historial_json = [*(paciente.historial_json or []), {
            "fecha_hora": paciente.actualizado_en.isoformat(), "usuario": usuario.strip(), "motivo": motivo.strip(),
            "anterior": anterior, "nuevo": nuevo,
        }]
        self.session.commit()
        self.session.refresh(paciente)
        return paciente
