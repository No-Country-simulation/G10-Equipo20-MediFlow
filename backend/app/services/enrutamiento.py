"""Enrutamiento (RN-E), notificación (RN-F, RN-Q) y armado del JSON final (RN-G).

Entrada: el resultado de la evaluación determinística (paso 8).
Salida: `ResultadoTriaje`, el contrato del brief con los campos agregados.

Principios:
- Tabla de decisión base por tipo y prioridad (RN-E2).
- Desde Urgencias u Hospitalizado nunca se espera autorización (RN-E4, RN-CO13).
- Nada con revisión humana llega a un destino final sin pasar por la cola (RN-E8);
  la única excepción es la alerta de un caso crítico (RN-D9).
- La alerta solo lleva ID de documento, nivel y enlace (RN-Q4).
"""
from dataclasses import dataclass

from app.packs.modelos import PackPais, Umbrales
from app.schemas.resultado import (
    DecisionRegistrada,
    Destino as D,
    Enrutamiento,
    EstadoDocumento as E,
    Evaluacion,
    Extraccion,
    MotivoAuditoria as M,
    NivelPrioridad as N,
    Notificacion,
    ResultadoTriaje,
    TipoDocumento as T,
)
from app.services.ciclo_vida import prefijo_storage
from app.services.evaluacion import Evaluado

_ORDEN_MOTIVOS = list(M)


@dataclass
class ContextoEnrutamiento:
    documento_id: str
    canal_origen: str
    pais: str
    version: int = 1
    url_base: str = "https://mediflow.local/documentos"
    posible_duplicado_de: str | None = None
    version_reglas: str = "8"


@dataclass
class _Plan:
    principal: D
    secundarios: list[D]
    motivos_destino: dict[str, str]
    justificacion: list[str]
    documentacion_incompleta: bool = False


class _Enrutador:
    def __init__(self, ev: Evaluado, ctx: ContextoEnrutamiento, pack: PackPais, umbrales: Umbrales):
        self.ev = ev
        self.ctx = ctx
        self.pack = pack
        self.u = umbrales
        self.motivos: list[M] = list(ev.motivos)
        self.historial: list[DecisionRegistrada] = list(ev.historial)

    def _registrar(self, regla: str, evidencia: str, decision: str) -> None:
        self.historial.append(DecisionRegistrada(regla=regla, evidencia=evidencia, decision=decision))

    def _agregar_motivo(self, motivo: M, regla: str, evidencia: str) -> None:
        if motivo not in self.motivos:
            self.motivos.append(motivo)
        self._registrar(regla, evidencia, f"revision_humana:{motivo.value}")

    @property
    def desde_urgencias(self) -> bool:
        return self.ctx.canal_origen in self.pack.urgencias.canales_sin_autorizacion

    # --- tabla de decisión base (RN-E2) --------------------------------------------

    def plan(self) -> _Plan:
        tipo, nivel = self.ev.clasificacion.tipo, self.ev.prioridad
        if tipo in (T.IMAGENES, T.LABORATORIO, T.NO_CLASIFICABLE):
            return self._plan_informe(nivel)
        if tipo is T.RECETA:
            return self._plan_receta(nivel)
        if tipo is T.ORDEN_PROCEDIMIENTO:
            return self._plan_orden(nivel)
        if tipo is T.EPICRISIS:
            return self._plan_epicrisis(nivel)
        return _Plan(D.HISTORIA_CLINICA_ELECTRONICA, [], {}, ["RN-E2: certificado a HCE"])

    def _plan_informe(self, nivel: N) -> _Plan:
        if nivel is N.CRITICO:
            return _Plan(D.COLA_EMERGENCIA_MEDICA, [D.HISTORIA_CLINICA_ELECTRONICA], {}, ["RN-E2: informe crítico a Emergencia + HCE"])
        if nivel is N.URGENTE:
            return _Plan(D.HISTORIA_CLINICA_ELECTRONICA, [], {}, ["RN-E2: informe urgente a HCE con aviso al solicitante (RN-F3)"])
        return _Plan(D.HISTORIA_CLINICA_ELECTRONICA, [], {}, ["RN-E2: informe de rutina a HCE"])

    def _plan_receta(self, nivel: N) -> _Plan:
        just = ["RN-E2: receta a Farmacia"]
        motivos: dict[str, str] = {}
        secundarios: list[D] = []
        if nivel is N.CRITICO:
            secundarios.append(D.COLA_EMERGENCIA_MEDICA)
            motivos[D.FARMACIA_HOSPITALARIA.value] = "farmacia_prioritaria"
            just.append("prioritaria + Emergencia por nivel Crítico")
        if self.ev.alto_riesgo:
            motivos.setdefault(D.FARMACIA_HOSPITALARIA.value, "alto_riesgo")
            just.append("RN-E6: alto_riesgo=true, exige doble verificación en Farmacia (RN-J6)")
        programa = self.pack.programas_cobertura.get("mipres")
        if programa is not None and not programa.activo:
            self._registrar("RN-CO14", f"lista UPC {programa.estado}", "mipres_no_evaluado")
        return _Plan(D.FARMACIA_HOSPITALARIA, secundarios, motivos, just)

    def _plan_orden(self, nivel: N) -> _Plan:
        aviso = self.pack.urgencias.motivo_aviso_auditoria
        if self.desde_urgencias:
            self._registrar("RN-CO13", f"canal {self.ctx.canal_origen}", "sin autorización previa; Auditoría solo como aviso")
            return _Plan(D.COLA_EMERGENCIA_MEDICA, [D.AUDITORIA_AUTORIZACIONES], {D.AUDITORIA_AUTORIZACIONES.value: aviso},
                         [f"RN-E4/RN-CO13: orden desde {self.ctx.canal_origen} a Emergencia sin autorización previa; Auditoría recibe {aviso}"])
        if nivel is N.CRITICO:
            return _Plan(D.COLA_EMERGENCIA_MEDICA, [D.AUDITORIA_AUTORIZACIONES], {D.AUDITORIA_AUTORIZACIONES.value: aviso},
                         ["RN-E2: orden crítica a Emergencia sin autorización previa; Auditoría como aviso"])

        plan = _Plan(D.AUDITORIA_AUTORIZACIONES, [], {}, ["RN-E2: orden ambulatoria a Auditoría"])
        if nivel is N.URGENTE:
            plan.motivos_destino[D.AUDITORIA_AUTORIZACIONES.value] = "via_rapida"
            plan.justificacion.append("vía rápida por nivel Urgente")
        self._cobertura(plan)
        self._documentacion_minima(plan)
        programa = self.pack.programas_cobertura.get("alto_costo")
        if programa is not None and not programa.activo:
            self._registrar("RN-CO15", f"lista de alto costo {programa.estado}", "rama inactiva (RN-E11)")
        return plan

    def _cobertura(self, plan: _Plan) -> None:
        """RN-E9, RN-E10, RN-E11, RN-CO12: el modelo de autorización depende de la cobertura."""
        cobertura = self.ev.cobertura
        if cobertura is None:
            self._agregar_motivo(M.COBERTURA_NO_INFORMADA, "RN-E10", "orden ambulatoria sin cobertura en el request ni en el documento")
            return
        definicion = self.pack.coberturas.get(cobertura)
        if definicion is None or definicion.estado != "verificado":
            estado = definicion.estado if definicion else "desconocida"
            self._agregar_motivo(M.COBERTURA_NO_CONFIGURADA, "RN-E11", f"cobertura {cobertura} en estado {estado}")
            return
        if definicion.modelo == "asegurador":
            plan.motivos_destino.setdefault(D.AUDITORIA_AUTORIZACIONES.value, "solicitud_autorizacion_eps")
            plan.justificacion.append(f"RN-E9/RN-CO12: cobertura {cobertura}, solicitud de autorización a la {definicion.entidad}")
        else:
            plan.motivos_destino.setdefault(D.AUDITORIA_AUTORIZACIONES.value, f"modelo_{definicion.modelo}")

    def _documentacion_minima(self, plan: _Plan) -> None:
        """RN-E5, RN-CO7: la orden a Auditoría lleva justificación, diagnóstico con código y CUPS."""
        faltantes: list[str] = []
        if not self.ev.justificacion_clinica:
            faltantes.append("justificacion_clinica")
        if not any(d.cie10_sugerido or d.cie11_sugerido for d in self.ev.diagnosticos):
            faltantes.append("diagnostico_codigo")
        if not any(p.cups for p in self.ev.procedimientos):
            faltantes.append("cups")
        if faltantes:
            plan.documentacion_incompleta = True
            plan.motivos_destino[D.AUDITORIA_AUTORIZACIONES.value] = "documentacion_incompleta"
            plan.justificacion.append(f"RN-E5: documentacion_incompleta, vuelve al solicitante (faltan {', '.join(faltantes)})")
            self._registrar("RN-E5", f"faltan {faltantes}", "documentacion_incompleta")

    def _plan_epicrisis(self, nivel: N) -> _Plan:
        secundarios: list[D] = []
        just = ["RN-E2: epicrisis a HCE"]
        if nivel is N.CRITICO:
            secundarios.append(D.COLA_EMERGENCIA_MEDICA)
            just.append("+ Emergencia por hallazgo pendiente")
        elif nivel is N.URGENTE:
            just.append("control en 7 días")
        programa = self.pack.programas_cobertura.get("alto_costo")
        if programa is not None and not programa.activo:
            self._registrar("RN-CO15", f"lista de alto costo {programa.estado}", "rama inactiva (RN-E11)")
        return _Plan(D.HISTORIA_CLINICA_ELECTRONICA, secundarios, {}, just)

    # --- notificación (RN-F, RN-Q) -----------------------------------------------------

    def notificacion(self) -> Notificacion | None:
        nivel = self.ev.prioridad
        enlace = f"{self.ctx.url_base}/{self.ctx.documento_id}"
        if nivel is N.CRITICO:
            self._registrar("RN-F1", "nivel Crítico", "alerta con acuse pendiente; escala a los 15 min (RN-F2)")
            return Notificacion(
                canal=self.u.notificaciones.canales[0],
                destinatario=self.u.notificaciones.cadena_guardia[0],
                mensaje=f"Alerta Crítica. Doc: {self.ctx.documento_id}. Nivel: Crítico. Requiere acuse.",
                enlace=enlace,
            )
        if nivel is N.URGENTE:
            self._registrar("RN-F3", "nivel Urgente", "aviso al profesional solicitante, sin escalamiento")
            return Notificacion(
                canal="Correo",
                destinatario="Profesional solicitante",
                mensaje=f"Aviso Urgente. Doc: {self.ctx.documento_id}. Nivel: Urgente. Atención en 24 h.",
                enlace=enlace,
            )
        return None  # RN-Q3: rutina no notifica

    # --- armado del resultado ---------------------------------------------------------

    def enrutar(self) -> ResultadoTriaje:
        plan = self.plan()
        self._registrar("RN-E2", f"tipo={self.ev.clasificacion.tipo.value} nivel={self.ev.prioridad.value}",
                        f"principal={plan.principal.value} secundarios={[d.value for d in plan.secundarios]}")
        inactivos = [d.value for d in (plan.principal, *plan.secundarios) if d.value in self.pack.destinos_inactivos]
        if inactivos:
            # RN-L1: la clínica desactivó ese destino. No se entrega solo: una persona decide qué hacer con el documento.
            self._agregar_motivo(M.DESTINO_INACTIVO, "RN-L1", f"destino desactivado en la configuración vigente: {', '.join(inactivos)}")
            plan.justificacion.append(f"RN-L1: {', '.join(inactivos)} está desactivado en esta instalación")

        entregas_retenidas: dict[str, str] = {}
        if self.ev.retiene_hce and D.HISTORIA_CLINICA_ELECTRONICA in (plan.principal, *plan.secundarios):
            entregas_retenidas[D.HISTORIA_CLINICA_ELECTRONICA.value] = "identidad_ausente_conciliar"
            self._registrar("RN-A4/RN-N3", "identidad ausente o temporal", "entrega a HCE retenida hasta conciliar")

        requiere_revision = bool(self.motivos)
        motivos_ordenados = sorted(self.motivos, key=_ORDEN_MOTIVOS.index) if requiere_revision else []
        motivo_principal = self.ev.motivo_principal if self.ev.motivos else (motivos_ordenados[0] if motivos_ordenados else None)

        if requiere_revision:
            self._registrar("RN-E8", f"motivos {[m.value for m in self.motivos]}", "Cola_Revision_Humana antes de cualquier destino final")
            enrutamiento = Enrutamiento(
                destino_principal=D.COLA_REVISION_HUMANA,
                destinos_secundarios=[],
                destinos_tras_revision=[plan.principal, *plan.secundarios],
                motivos_destino=plan.motivos_destino,
                entregas_retenidas=entregas_retenidas,
                documentacion_incompleta=plan.documentacion_incompleta,
                justificacion_enrutamiento="RN-E8: requiere revisión humana; plan tras revisión: " + "; ".join(plan.justificacion),
            )
            estado = E.EN_REVISION_HUMANA
        else:
            enrutamiento = Enrutamiento(
                destino_principal=plan.principal,
                destinos_secundarios=plan.secundarios,
                motivos_destino=plan.motivos_destino,
                entregas_retenidas=entregas_retenidas,
                documentacion_incompleta=plan.documentacion_incompleta,
                justificacion_enrutamiento="; ".join(plan.justificacion),
            )
            estado = E.ENRUTADO

        notificacion = self.notificacion()  # RN-D9: la alerta se emite aunque vaya a revisión
        sufijo = f"_v{self.ctx.version}" if self.ctx.version > 1 else ""
        prefijo = prefijo_storage(estado, self.ctx.pais, nivel=self.ev.prioridad.value)
        ruta = f"{prefijo}/{self.ctx.documento_id}{sufijo}.json"

        return ResultadoTriaje(
            documento_id=self.ctx.documento_id,
            clasificacion=self.ev.clasificacion,
            extraccion=Extraccion(
                paciente=self.ev.paciente,
                profesional=self.ev.profesional,
                fecha_documento=self.ev.fecha_documento,
                signos_vitales=self.ev.signos_vitales,
                diagnosticos=self.ev.diagnosticos,
                procedimientos=self.ev.procedimientos,
                medicamentos=self.ev.medicamentos,
                hallazgos_criticos_detectados=self.ev.hallazgos,
            ),
            evaluacion=Evaluacion(
                requiere_auditoria_humana=requiere_revision,
                motivo_auditoria=motivo_principal if requiere_revision else None,
                campos_dudosos=self.ev.campos_dudosos,
            ),
            enrutamiento=enrutamiento,
            notificacion_generada=notificacion,
            estado=estado,
            pack_pais=self.pack.pais,
            version_reglas=self.ctx.version_reglas,
            historial_decisiones=self.historial,
            ruta_storage=ruta,
            posible_duplicado_de=self.ctx.posible_duplicado_de,
        )


def enrutar(evaluado: Evaluado, contexto: ContextoEnrutamiento, pack: PackPais, umbrales: Umbrales) -> ResultadoTriaje:
    return _Enrutador(evaluado, contexto, pack, umbrales).enrutar()
