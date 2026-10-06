"""Gobierno de la configuración (dominio L).

RN-L1: el gestor mueve los umbrales de confianza, tolerancia y plazos solo dentro de su rango.
RN-L2: NEWS2, seudonimización y separación de funciones no se configuran.
RN-L3: hallazgos críticos, alto riesgo y control especial solo se amplían.
RN-L4: cada cambio es una versión nueva con autor, fecha y vigencia; no es retroactiva.
RN-L5: un cambio que toca seguridad exige dos aprobadores distintos.
RN-L6: antes de activar, se simula sobre los últimos documentos.
"""
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.documento import Documento
from app.models.gobierno import VersionConfiguracion
from app.models.referencia import CasoReferencia
from app.packs.loader import cargar_pack, cargar_umbrales
from app.packs.modelos import HallazgoCritico, PackPais, Umbrales
from app.schemas.resultado import Destino, ResultadoTriaje
from app.services.compuerta import comparar_configuraciones

# Claves configurables (RN-L1) con su ruta dentro de Umbrales. Todo lo demás no se configura (RN-L2).
CONFIGURABLES: dict[str, tuple[str, ...]] = {
    "confianza.clasificacion": ("confianza", "clasificacion"),
    "confianza.identidad_paciente": ("confianza", "identidad_paciente"),
    "confianza.medicamento_dosis": ("confianza", "medicamento_dosis"),
    "confianza.diagnostico_codigo": ("confianza", "diagnostico_codigo"),
    "confianza.profesional": ("confianza", "profesional"),
    "confianza.resto": ("confianza", "resto"),
    "consistencia.tolerancia_edad_anios": ("consistencia", "tolerancia_edad_anios"),
    "tiempos.comunicacion_critico_min": ("tiempos", "comunicacion_critico_min"),
    "tiempos.escalamiento_sin_acuse_min": ("tiempos", "escalamiento_sin_acuse_min"),
    "tiempos.atencion_urgente_h": ("tiempos", "atencion_urgente_h"),
    "tiempos.cola_revision.critico_min": ("tiempos", "cola_revision", "critico_min"),
    "tiempos.cola_revision.urgente_h": ("tiempos", "cola_revision", "urgente_h"),
    "tiempos.cola_revision.rutina_h_habiles": ("tiempos", "cola_revision", "rutina_h_habiles"),
}
# RN-L2: por estos dos pasa la seguridad del paciente (alerta crítica, RN-F1; revisión humana, RN-E8). Nunca se desactivan.
DESTINOS_PROTEGIDOS = (Destino.COLA_EMERGENCIA_MEDICA, Destino.COLA_REVISION_HUMANA)
_EPSILON = 1e-9


class ErrorConfiguracion(Exception):
    def __init__(self, detalle: str, codigo: int = 422):
        super().__init__(detalle)
        self.detalle = detalle
        self.codigo = codigo


class HallazgoAmpliado(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concepto: str = Field(..., min_length=3)
    sinonimos: list[str] = Field(default_factory=list)
    cie10: list[str] = Field(default_factory=list)
    cie11: list[str] = Field(default_factory=list)


class Ampliaciones(BaseModel):
    """RN-L3: solo hay campos para agregar. Quitar no existe en el esquema."""

    model_config = ConfigDict(extra="forbid")

    alto_riesgo: list[str] = Field(default_factory=list)
    control_especial: list[str] = Field(default_factory=list)
    hallazgos_criticos: list[HallazgoAmpliado] = Field(default_factory=list)

    @property
    def vacias(self) -> bool:
        return not (self.alto_riesgo or self.control_especial or self.hallazgos_criticos)


class CambiosConfiguracion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    umbrales: dict[str, float] = Field(default_factory=dict)
    ampliaciones: Ampliaciones = Field(default_factory=Ampliaciones)
    # RN-L1: destinos que la clínica no usa. None: la versión no los toca; una lista: el conjunto completo desde esa versión.
    destinos_inactivos: list[Destino] | None = None

    @property
    def vacios(self) -> bool:
        return not self.umbrales and self.ampliaciones.vacias and self.destinos_inactivos is None


# --- Reglas puras -----------------------------------------------------------------------------


def acumular(previos: CambiosConfiguracion, nuevos: CambiosConfiguracion) -> CambiosConfiguracion:
    """RN-L4: cada versión guarda solo lo que cambió; lo vigente es la suma de todas las que entraron en vigencia.
    Un umbral toma su último valor. RN-L3: las listas se unen, así una versión posterior nunca quita lo ampliado."""
    a, b = previos.ampliaciones, nuevos.ampliaciones
    conceptos = {h.concepto.strip().upper() for h in a.hallazgos_criticos}
    return CambiosConfiguracion(
        umbrales={**previos.umbrales, **nuevos.umbrales},
        ampliaciones=Ampliaciones(
            alto_riesgo=_agregar_sin_repetir(a.alto_riesgo, b.alto_riesgo),
            control_especial=_agregar_sin_repetir(a.control_especial, b.control_especial),
            hallazgos_criticos=[*a.hallazgos_criticos, *(h for h in b.hallazgos_criticos if h.concepto.strip().upper() not in conceptos)],
        ),
        destinos_inactivos=nuevos.destinos_inactivos if nuevos.destinos_inactivos is not None else previos.destinos_inactivos,
    )


def validar_destinos(cambios: CambiosConfiguracion) -> None:
    for destino in cambios.destinos_inactivos or []:
        if destino in DESTINOS_PROTEGIDOS:
            raise ErrorConfiguracion(f"RN-L2: {destino.value} no se desactiva; por ahí pasan las alertas críticas y la revisión humana")


def _leer(datos: dict, ruta: tuple[str, ...]) -> Any:
    for parte in ruta:
        datos = datos[parte]
    return datos


def _escribir(datos: dict, ruta: tuple[str, ...], valor: Any) -> None:
    for parte in ruta[:-1]:
        datos = datos[parte]
    datos[ruta[-1]] = valor


def valor_base(base: Umbrales, clave: str) -> float:
    return _leer(base.model_dump(), CONFIGURABLES[clave])


def aplicar_umbrales(base: Umbrales, cambios: CambiosConfiguracion) -> Umbrales:
    """Devuelve umbrales nuevos con los cambios aplicados. Falla si algo está fuera de rango o no es configurable."""
    datos = base.model_dump()
    for clave, valor in cambios.umbrales.items():
        if clave not in CONFIGURABLES:
            raise ErrorConfiguracion(f"RN-L2: {clave} no es configurable. Solo: {', '.join(CONFIGURABLES)}")
        rango = base.rangos.get(clave)
        if rango is None:
            raise ErrorConfiguracion(f"RN-L1: {clave} no tiene rango definido en umbrales.yaml")
        actual = _leer(datos, CONFIGURABLES[clave])
        if rango.solo_a_la_baja and valor > actual + _EPSILON:
            raise ErrorConfiguracion(f"RN-D1: {clave} se configura solo a la baja (base {actual}, pedido {valor})")
        if valor < rango.min - _EPSILON or valor > rango.max + _EPSILON:
            raise ErrorConfiguracion(f"RN-L1: {clave}={valor} fuera del rango [{rango.min}, {rango.max}]")
        tipo = type(actual)
        _escribir(datos, CONFIGURABLES[clave], tipo(valor) if tipo in (int, float) else valor)
    return Umbrales.model_validate(datos)


def _agregar_sin_repetir(base: list[str], nuevos: list[str]) -> list[str]:
    vistos = {x.strip().lower() for x in base}
    salida = list(base)
    for nuevo in nuevos:
        limpio = nuevo.strip().lower()
        if limpio and limpio not in vistos:
            salida.append(limpio)
            vistos.add(limpio)
    return salida


def aplicar_pack(base: PackPais, cambios: CambiosConfiguracion) -> PackPais:
    """RN-L3: agrega a las listas del pack. Los elementos base siempre quedan."""
    a = cambios.ampliaciones
    pack = base.model_copy(deep=True)
    pack.medicamentos.alto_riesgo = _agregar_sin_repetir(pack.medicamentos.alto_riesgo, a.alto_riesgo)
    pack.medicamentos.control_especial = _agregar_sin_repetir(pack.medicamentos.control_especial, a.control_especial)
    conceptos = {h.concepto for h in pack.hallazgos_criticos}
    for h in a.hallazgos_criticos:
        concepto = h.concepto.strip().upper().replace(" ", "_")
        if concepto in conceptos:
            continue
        pack.hallazgos_criticos.append(HallazgoCritico(concepto=concepto, cie10=h.cie10, cie11=h.cie11, sinonimos=h.sinonimos,
                                                       estado="por_confirmar"))
        conceptos.add(concepto)
    if cambios.destinos_inactivos is not None:
        pack.destinos_inactivos = sorted({d.value for d in cambios.destinos_inactivos})
    return pack


def toca_seguridad(base: Umbrales, cambios: CambiosConfiguracion, inactivos_actuales: list[str] | None = None) -> bool:
    """RN-L5: baja de confianza, más tolerancia, más tiempo de reacción o un destino que deja de recibir tocan seguridad."""
    if cambios.destinos_inactivos is not None and {d.value for d in cambios.destinos_inactivos} - set(inactivos_actuales or []):
        return True
    for clave, valor in cambios.umbrales.items():
        if clave not in CONFIGURABLES:
            continue
        actual = valor_base(base, clave)
        if clave.startswith("confianza.") and valor < actual - _EPSILON:
            return True
        if (clave.startswith("consistencia.") or clave.startswith("tiempos.")) and valor > actual + _EPSILON:
            return True
    return False


def aprobaciones_requeridas(toca: bool) -> int:
    return 2 if toca else 1


# --- Servicio con persistencia -----------------------------------------------------------------


class ServicioConfiguracion:
    def __init__(self, session: Session):
        self.session = session

    # lectura

    def vigente(self) -> VersionConfiguracion | None:
        return self.session.scalars(select(VersionConfiguracion).where(VersionConfiguracion.estado == "vigente")).first()

    def cambios_vigentes(self) -> CambiosConfiguracion:
        """Suma, en orden, de todas las versiones que entraron en vigencia (las rechazadas no tienen número)."""
        versiones = self.session.scalars(select(VersionConfiguracion).where(VersionConfiguracion.numero.is_not(None))
                                         .order_by(VersionConfiguracion.numero))
        acumulado = CambiosConfiguracion()
        for v in versiones:
            acumulado = acumular(acumulado, CambiosConfiguracion.model_validate(v.cambios_json))
        return acumulado

    def umbrales(self) -> Umbrales:
        return aplicar_umbrales(cargar_umbrales(), self.cambios_vigentes())

    def pack(self, pais: str) -> PackPais:
        return aplicar_pack(cargar_pack(pais), self.cambios_vigentes())

    def propuestas(self) -> list[VersionConfiguracion]:
        return list(self.session.scalars(select(VersionConfiguracion).where(VersionConfiguracion.estado == "propuesta").order_by(VersionConfiguracion.id)))

    def historial(self) -> list[VersionConfiguracion]:
        return list(self.session.scalars(select(VersionConfiguracion).where(VersionConfiguracion.estado != "propuesta").order_by(VersionConfiguracion.id.desc())))

    def por_id(self, id_: int) -> VersionConfiguracion:
        v = self.session.get(VersionConfiguracion, id_)
        if v is None:
            raise ErrorConfiguracion("propuesta no encontrada", 404)
        return v

    # escritura

    def validar(self, cambios: CambiosConfiguracion, pais: str) -> tuple[Umbrales, PackPais]:
        if cambios.vacios:
            raise ErrorConfiguracion("RN-L4: una versión necesita al menos un cambio")
        validar_destinos(cambios)
        return aplicar_umbrales(self.umbrales(), cambios), aplicar_pack(self.pack(pais), cambios)

    def proponer(self, cambios: CambiosConfiguracion, *, autor: str, motivo: str, pais: str, simulacion: dict | None) -> VersionConfiguracion:
        if not motivo.strip():
            raise ErrorConfiguracion("RN-L4: cada versión lleva su motivo")
        self.validar(cambios, pais)
        v = VersionConfiguracion(autor=autor.strip(), motivo=motivo.strip(), cambios_json=cambios.model_dump(mode="json"),
                                 simulacion_json=simulacion, aprobaciones_json=[],
                                 toca_seguridad=toca_seguridad(self.umbrales(), cambios, self.pack(pais).destinos_inactivos))
        self.session.add(v)
        self.session.commit()
        self.session.refresh(v)
        return v

    def aprobar(self, id_: int, usuario: str, *, pais: str) -> VersionConfiguracion:
        v = self.por_id(id_)
        if v.estado != "propuesta":
            raise ErrorConfiguracion(f"la versión ya está {v.estado}", 409)
        aprobaciones = list(v.aprobaciones_json or [])
        if any(a["usuario"] == usuario for a in aprobaciones):
            raise ErrorConfiguracion("RN-L5: los aprobadores deben ser personas distintas", 409)
        activa = len(aprobaciones) + 1 >= aprobaciones_requeridas(v.toca_seguridad)
        if activa:
            # RN-R3: la compuerta corre con el conjunto de referencia de hoy, no con el del día de la propuesta.
            compuerta = self.compuerta(CambiosConfiguracion.model_validate(v.cambios_json), pais)
            v.simulacion_json = {**(v.simulacion_json or {}), "compuerta": compuerta}
            if compuerta["empeora"]:
                self.session.commit()
                raise ErrorConfiguracion("RN-R3: la versión empeora los falsos negativos críticos sobre el conjunto de referencia "
                                         f"({compuerta['actual']['falsos_negativos']} -> {compuerta['propuesto']['falsos_negativos']}; "
                                         f"nuevos: {', '.join(compuerta['nuevos_falsos_negativos'])}) y no se activa", 409)
        aprobaciones.append({"usuario": usuario, "fecha_hora": datetime.now(timezone.utc).isoformat()})
        v.aprobaciones_json = aprobaciones
        if activa:
            self._activar(v)
        self.session.commit()
        self.session.refresh(v)
        return v

    def rechazar(self, id_: int, usuario: str, motivo: str) -> VersionConfiguracion:
        v = self.por_id(id_)
        if v.estado != "propuesta":
            raise ErrorConfiguracion(f"la versión ya está {v.estado}", 409)
        v.estado = "rechazada"
        v.cierre_por = usuario
        v.cierre_motivo = motivo
        self.session.commit()
        self.session.refresh(v)
        return v

    def _activar(self, v: VersionConfiguracion) -> None:
        ahora = datetime.now(timezone.utc)
        anterior = self.vigente()
        if anterior is not None:
            anterior.estado = "reemplazada"
            anterior.vigente_hasta = ahora
        ultimo = self.session.scalar(select(func.max(VersionConfiguracion.numero))) or 0
        v.numero = ultimo + 1
        v.estado = "vigente"
        v.vigente_desde = ahora

    # compuerta de calidad (RN-R3)

    def casos_referencia(self) -> list[CasoReferencia]:
        return list(self.session.scalars(select(CasoReferencia).order_by(CasoReferencia.id)))

    def compuerta(self, cambios: CambiosConfiguracion, pais: str) -> dict:
        """Falsos negativos críticos sobre el conjunto de referencia con la configuración vigente y con la propuesta."""
        umbrales, pack = self.validar(cambios, pais)
        return comparar_configuraciones(self.casos_referencia(), (self.pack(pais), self.umbrales()), (pack, umbrales))

    # simulación (RN-L6)

    def simular(self, cambios: CambiosConfiguracion, *, pais: str, ultimos: int,
                recalcular: Callable[[Documento, PackPais, Umbrales], ResultadoTriaje]) -> dict:
        umbrales, pack = self.validar(cambios, pais)
        documentos = list(self.session.scalars(select(Documento).order_by(Documento.id.desc()).limit(ultimos)))
        detalle: list[dict] = []
        sin_propuesta = 0
        evaluados = 0
        for doc in documentos:
            if not doc.propuesta_json or not doc.resultado_json:
                sin_propuesta += 1
                continue
            actual = ResultadoTriaje.model_validate(doc.resultado_json)
            nuevo = recalcular(doc, pack, umbrales)
            evaluados += 1
            fila = {
                "documento_id": doc.documento_id,
                "version": doc.version,
                "tipo": actual.clasificacion.tipo.value,
                "estado_actual": actual.estado.value,
                "estado_simulado": nuevo.estado.value,
                "prioridad_actual": actual.clasificacion.nivel_prioridad.value,
                "prioridad_simulada": nuevo.clasificacion.nivel_prioridad.value,
                "motivo_actual": actual.evaluacion.motivo_auditoria.value if actual.evaluacion.motivo_auditoria else None,
                "motivo_simulado": nuevo.evaluacion.motivo_auditoria.value if nuevo.evaluacion.motivo_auditoria else None,
                "destino_actual": actual.enrutamiento.destino_principal.value,
                "destino_simulado": nuevo.enrutamiento.destino_principal.value,
            }
            fila["cambia"] = (fila["estado_actual"] != fila["estado_simulado"] or fila["prioridad_actual"] != fila["prioridad_simulada"]
                              or fila["motivo_actual"] != fila["motivo_simulado"] or fila["destino_actual"] != fila["destino_simulado"])
            if fila["cambia"]:
                detalle.append(fila)
        a_revision = sum(1 for f in detalle if f["estado_simulado"] == "EN_REVISION_HUMANA" and f["estado_actual"] != "EN_REVISION_HUMANA")
        automaticos = sum(1 for f in detalle if f["estado_actual"] == "EN_REVISION_HUMANA" and f["estado_simulado"] != "EN_REVISION_HUMANA")
        return {
            "documentos_evaluados": evaluados,
            "sin_propuesta": sin_propuesta,
            "cambian": len(detalle),
            "mas_a_revision": a_revision,
            "mas_automaticos": automaticos,
            "detalle": detalle,
            "compuerta": self.compuerta(cambios, pais),  # RN-R3
        }
