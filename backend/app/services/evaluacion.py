"""Evaluación determinística sobre la propuesta del LLM (estado EVALUADO).

Aquí se aplican las reglas del pipeline clínico que no dependen del LLM:
clasificación (RN-B), extracción y consistencia (RN-C), prioridad (RN-D),
identidad (RN-A4, RN-CO1 a CO3), fórmula médica (RN-CO8 a CO10) y poblaciones
especiales (RN-N). El resultado alimenta el enrutamiento (paso 9).

Regla de oro: el código puede subir la prioridad que propuso el LLM, nunca bajarla (RN-D8).
"""
import re
import unicodedata
from dataclasses import dataclass, field

from app.packs.fechas import formatear_fecha, parsear_fecha
from app.packs.identidad import ResultadoIdentidad, validar_identidad_paciente
from app.packs.modelos import PackPais, Umbrales
from app.packs.numeros import detectar_convencion, parsear_cantidad
from app.schemas.propuesta import PropuestaLLM
from app.schemas.resultado import (
    Clasificacion,
    DecisionRegistrada,
    Diagnostico,
    DocumentoPaciente,
    EstadoIdentidad,
    Medicamento,
    MotivoAuditoria as M,
    NivelPrioridad as N,
    Paciente,
    Procedimiento,
    Profesional,
    SignosVitales,
    TipoDocumento as T,
    TipoDocumentoPaciente,
)
from app.services.hallazgos import Deteccion, detectar_hallazgos
from app.services.news2 import ResultadoNEWS2, calcular_news2

_ORDEN_PRIORIDAD = {N.RUTINA: 0, N.URGENTE: 1, N.CRITICO: 2}

# Orden de severidad de los motivos: el primero es el motivo_auditoria del JSON.
_SEVERIDAD = [
    M.FALLO_TECNICO, M.ILEGIBLE, M.NO_CLASIFICABLE, M.CLASIFICACION_BAJA_CONFIANZA, M.FUERA_DE_ALCANCE,
    M.CRITICO_BAJA_CONFIANZA, M.CONTROL_ESPECIAL_SIN_RECETARIO, M.RECETA_INCOMPLETA_NORMA, M.DOSIS_AMBIGUA,
    M.IDENTIDAD_INVALIDA, M.AMBIGUO, M.PROFESIONAL_NO_IDENTIFICABLE, M.CAMPO_OBLIGATORIO_FALTANTE,
    M.FECHA_AMBIGUA, M.SIGNOS_VITALES_SIN_ESCALA, M.CAMPO_DUDOSO, M.DOCUMENTACION_INCOMPLETA,
    M.COBERTURA_NO_INFORMADA, M.COBERTURA_NO_CONFIGURADA,
]

_INFORMES = {T.IMAGENES, T.LABORATORIO}

_NUMEROS_EN_LETRAS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veintiun": 21,
    "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23, "veinticuatro": 24, "veinticinco": 25,
    "veintiseis": 26, "veintisiete": 27, "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
    "doscientos": 200, "doscientas": 200, "trescientos": 300, "trescientas": 300, "cuatrocientos": 400,
    "cuatrocientas": 400, "quinientos": 500, "quinientas": 500, "seiscientos": 600, "seiscientas": 600,
    "setecientos": 700, "setecientas": 700, "ochocientos": 800, "ochocientas": 800, "novecientos": 900,
    "novecientas": 900,
}


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower().strip()


def numero_en_letras(texto: str | None) -> int | None:
    """'treinta' -> 30, 'ciento veinte' -> 120, 'dos mil' -> 2000. None si no se puede leer."""
    if not texto:
        return None
    palabras = [p for p in re.split(r"[\s\-]+", _sin_tildes(re.sub(r"[()]", "", texto))) if p and p != "y"]
    total, actual = 0, 0
    for palabra in palabras:
        if palabra == "mil":
            total += (actual or 1) * 1000
            actual = 0
        elif palabra in _NUMEROS_EN_LETRAS:
            actual += _NUMEROS_EN_LETRAS[palabra]
        else:
            return None
    return total + actual


@dataclass
class ContextoEvaluacion:
    canal_origen: str
    pais: str
    cobertura_request: str | None
    texto: str  # texto seudonimizado del documento; vacío en la ruta de imagen
    prioridad_humana: N | None = None  # RN-J5: nivel fijado por una persona en revisión
    usuario_humano: str | None = None


@dataclass
class Evaluado:
    clasificacion: Clasificacion
    prioridad_propuesta: N
    paciente: Paciente
    profesional: Profesional
    fecha_documento: str | None
    signos_vitales: SignosVitales
    diagnosticos: list[Diagnostico]
    procedimientos: list[Procedimiento]
    medicamentos: list[Medicamento]
    hallazgos: list[str]
    detecciones: list[Deteccion]
    news2: ResultadoNEWS2
    identidad: ResultadoIdentidad
    cobertura: str | None
    justificacion_clinica: str | None
    motivos: list[M] = field(default_factory=list)
    campos_dudosos: list[str] = field(default_factory=list)
    historial: list[DecisionRegistrada] = field(default_factory=list)

    @property
    def prioridad(self) -> N:
        return self.clasificacion.nivel_prioridad

    @property
    def requiere_auditoria_humana(self) -> bool:
        return bool(self.motivos)

    @property
    def motivo_principal(self) -> M | None:
        return self.motivos[0] if self.motivos else None

    @property
    def retiene_hce(self) -> bool:
        return self.identidad.retiene_hce

    @property
    def alto_riesgo(self) -> bool:
        return any(m.alto_riesgo for m in self.medicamentos)

    @property
    def control_especial(self) -> bool:
        return any(m.control_especial for m in self.medicamentos)


class _Evaluador:
    def __init__(self, propuesta: PropuestaLLM, contexto: ContextoEvaluacion, pack: PackPais, umbrales: Umbrales):
        self.p = propuesta
        self.ctx = contexto
        self.pack = pack
        self.u = umbrales
        self.motivos: set[M] = set()
        self.dudosos: list[str] = list(propuesta.campos_dudosos)
        self.historial: list[DecisionRegistrada] = []

    # --- utilidades -------------------------------------------------------------

    def _registrar(self, regla: str, evidencia: str, decision: str, propuesta_llm: str | None = None) -> None:
        self.historial.append(DecisionRegistrada(regla=regla, evidencia=evidencia, propuesta_llm=propuesta_llm, decision=decision))

    def _motivo(self, motivo: M, regla: str, evidencia: str, *campos: str) -> None:
        self.motivos.add(motivo)
        for campo in campos:
            if campo not in self.dudosos:
                self.dudosos.append(campo)
        self._registrar(regla, evidencia, f"revision_humana:{motivo.value}")

    @property
    def tipo(self) -> T:
        return self.p.clasificacion.tipo

    # --- reglas -------------------------------------------------------------------

    def clasificacion(self) -> None:
        c = self.p.clasificacion
        if c.tipo is T.NO_CLASIFICABLE:
            self._motivo(M.NO_CLASIFICABLE, "RN-B4", "tipo No Clasificable")
        if not self.u.supera("clasificacion", c.score_confianza):
            self._motivo(M.CLASIFICACION_BAJA_CONFIANZA, "RN-B4", f"score_confianza={c.score_confianza}", "clasificacion.tipo")
        if c.dominio.value == "Otro" and c.tipo is not T.CERTIFICADO:
            self._motivo(M.FUERA_DE_ALCANCE, "RN-B3", "dominio Otro en informe clínico")
        if self.u.confianza.texto_ilegible_max is not None and self.p.condiciones.porcentaje_ilegible > self.u.confianza.texto_ilegible_max:
            self._motivo(M.ILEGIBLE, "RN-C5", f"porcentaje_ilegible={self.p.condiciones.porcentaje_ilegible}")

    def identidad(self) -> ResultadoIdentidad:
        pac = self.p.extraccion.paciente
        r = validar_identidad_paciente(pac.documento.tipo, pac.documento.valor, edad=pac.edad, pack=self.pack)
        self._registrar("RN-A4", f"tipo={r.tipo} estado={r.estado.value}", "retiene_hce" if r.retiene_hce else "sin_efecto")
        if r.estado is EstadoIdentidad.INVALIDO:
            self._motivo(M.IDENTIDAD_INVALIDA, "RN-A4", f"documento {r.tipo} no cumple formato del pack (RN-CO1)", "documento.valor")
        if r.coherente_con_edad is False:
            self._motivo(M.AMBIGUO, "RN-CO2", f"documento {r.tipo} incoherente con edad {pac.edad}", "documento.tipo", "edad")
        if r.identificador_temporal:
            self._registrar("RN-CO3", f"paciente no identificado {r.tipo}", f"identificador temporal {r.identificador_temporal}")
        return r

    def campos_obligatorios(self, identidad: ResultadoIdentidad) -> None:
        e = self.p.extraccion
        faltantes: list[str] = []
        no_identificado = identidad.identificador_temporal is not None
        if not no_identificado and not e.paciente.nombre:
            faltantes.append("paciente.nombre")
        if not no_identificado and e.paciente.edad is None:
            faltantes.append("paciente.edad")
        if not (e.profesional.nombre or e.profesional.registro_profesional):
            faltantes.append("profesional")
        if not e.fecha_documento:
            faltantes.append("fecha_documento")

        if self.tipo in _INFORMES:
            if not e.procedimientos:
                faltantes.append("procedimientos")
            if not any(d.cie10_sugerido or d.cie11_sugerido for d in e.diagnosticos):
                faltantes.append("diagnosticos.codigo")
        elif self.tipo is T.ORDEN_PROCEDIMIENTO:
            # RN-C1: procedimiento e indicación (diagnóstico con código). La justificación
            # ampliada de RN-E5 la evalúa el enrutamiento como documentacion_incompleta.
            if not e.procedimientos:
                faltantes.append("procedimientos")
            if not any(d.cie10_sugerido or d.cie11_sugerido for d in e.diagnosticos):
                faltantes.append("diagnosticos.codigo")
        elif self.tipo is T.EPICRISIS:
            if not e.diagnosticos:
                faltantes.append("diagnosticos")
        elif self.tipo is T.RECETA:
            faltantes += self._faltantes_receta(identidad)

        if not faltantes:
            return
        if self.tipo is T.RECETA:
            self._motivo(M.RECETA_INCOMPLETA_NORMA, "RN-CO8", f"faltan: {', '.join(faltantes)}", *faltantes)
        else:
            self._motivo(M.CAMPO_OBLIGATORIO_FALTANTE, "RN-C1", f"faltan: {', '.join(faltantes)}", *faltantes)

    def _faltantes_receta(self, identidad: ResultadoIdentidad) -> list[str]:
        e = self.p.extraccion
        faltantes: list[str] = []
        if identidad.estado is EstadoIdentidad.AUSENTE:
            faltantes.append("paciente.documento")  # RN-CO8: en recetas el documento sí es obligatorio
        if not e.profesional.registro_profesional:
            faltantes.append("profesional.registro_profesional")
        if not e.medicamentos:
            faltantes.append("medicamentos")
        campos = ("dosis", "via", "frecuencia", "duracion", "concentracion", "forma_farmaceutica", "cantidad_numeros", "cantidad_letras")
        for i, m in enumerate(e.medicamentos):
            faltantes += [f"medicamentos[{i}].{campo}" for campo in campos if not getattr(m, campo)]
        if self.tipo is T.RECETA and not (e.profesional.nombre or e.profesional.registro_profesional):
            self._motivo(M.PROFESIONAL_NO_IDENTIFICABLE, "RN-A8", "receta sin profesional identificable", "profesional")
        return faltantes

    def confianzas(self, hallazgos: list[Deteccion]) -> None:
        c = self.p.confianzas
        e = self.p.extraccion

        def bajo(campo: str, valor: float | None) -> bool:
            return valor is None or not self.u.supera(campo, valor)

        if e.paciente.documento.valor and bajo("identidad_paciente", c.identidad_paciente):
            self._motivo(M.CAMPO_DUDOSO, "RN-C3", f"identidad_paciente={c.identidad_paciente}", "identidad_paciente")
        if e.medicamentos and bajo("medicamento_dosis", c.medicamento_dosis):
            self._motivo(M.CAMPO_DUDOSO, "RN-C3", f"medicamento_dosis={c.medicamento_dosis}", "medicamento_dosis")
        if e.diagnosticos and bajo("diagnostico_codigo", c.diagnostico_codigo):
            self._motivo(M.CAMPO_DUDOSO, "RN-C3", f"diagnostico_codigo={c.diagnostico_codigo}", "diagnostico_codigo")
            if hallazgos:
                self._motivo(M.CRITICO_BAJA_CONFIANZA, "RN-D9", "hallazgo crítico con confianza baja: alerta inmediata y revisión")
        if (e.profesional.nombre or e.profesional.registro_profesional) and bajo("profesional", c.profesional):
            self._motivo(M.CAMPO_DUDOSO, "RN-C3", f"profesional={c.profesional}", "profesional")
        if hallazgos and not self.u.supera("clasificacion", self.p.clasificacion.score_confianza):
            self._motivo(M.CRITICO_BAJA_CONFIANZA, "RN-D9", "hallazgo crítico con clasificación de baja confianza")

    def medicamentos(self) -> list[Medicamento]:
        convencion = detectar_convencion(self.ctx.texto or "")
        alto_riesgo = {_sin_tildes(x) for x in self.pack.medicamentos.alto_riesgo}
        control = {_sin_tildes(x) for x in self.pack.medicamentos.control_especial}
        salida: list[Medicamento] = []
        for i, m in enumerate(self.p.extraccion.medicamentos):
            dci = _sin_tildes(m.dci)  # RN-C9: principio activo antes de evaluar riesgo
            es_alto = dci in alto_riesgo
            es_control = dci in control
            dosis_valor = None
            if m.dosis:
                cantidad = parsear_cantidad(m.dosis, convencion=convencion, pack=self.pack)
                if cantidad.ambigua:
                    self._motivo(M.DOSIS_AMBIGUA, "RN-CO10", f"dosis '{m.dosis}' con convención {convencion.value}", f"medicamentos[{i}].dosis")
                else:
                    dosis_valor = format(cantidad.valor.normalize(), "f")
            if m.cantidad_numeros and m.cantidad_letras:
                en_numeros = re.sub(r"\D", "", m.cantidad_numeros)
                en_letras = numero_en_letras(m.cantidad_letras)
                if en_numeros and en_letras is not None and int(en_numeros) != en_letras:
                    self._motivo(M.AMBIGUO, "RN-CO8", f"cantidad {m.cantidad_numeros} ({m.cantidad_letras}) no coincide", f"medicamentos[{i}].cantidad")
            if es_alto:
                self._registrar("RN-E6", f"{dci} en lista de alto riesgo", "alto_riesgo=true; doble verificación en Farmacia")
            salida.append(
                Medicamento(
                    dci=dci, dosis=m.dosis, dosis_valor=dosis_valor, concentracion=m.concentracion,
                    forma_farmaceutica=m.forma_farmaceutica, via=m.via, frecuencia=m.frecuencia, duracion=m.duracion,
                    cantidad_numeros=m.cantidad_numeros, cantidad_letras=m.cantidad_letras,
                    alto_riesgo=es_alto, control_especial=es_control,
                )
            )
        if self.tipo is T.RECETA and any(x.control_especial for x in salida) and self.p.condiciones.recetario_oficial is not True:
            self._motivo(M.CONTROL_ESPECIAL_SIN_RECETARIO, "RN-CO9", "medicamento de control especial sin recetario oficial acreditado")
        return salida

    def fecha(self) -> str | None:
        original = self.p.extraccion.fecha_documento
        if not original:
            return None
        valor = parsear_fecha(original, self.pack)
        if valor is None:
            if self.tipo in (T.RECETA, T.ORDEN_PROCEDIMIENTO):
                self._motivo(M.FECHA_AMBIGUA, "RN-C8", f"fecha '{original}' no se puede leer", "fecha_documento")
            elif "fecha_documento" not in self.dudosos:
                self.dudosos.append("fecha_documento")
            return None
        return formatear_fecha(valor, self.pack)

    def news2(self) -> ResultadoNEWS2:
        r = calcular_news2(
            self.p.extraccion.signos_vitales,
            edad=self.p.extraccion.paciente.edad,
            umbrales=self.u,
            epoc_hipercapnico=self.p.condiciones.epoc_hipercapnico,
            embarazo=self.p.condiciones.embarazo,
        )
        if r.hay_signos and not r.aplicable:
            self._motivo(M.SIGNOS_VITALES_SIN_ESCALA, "RN-N1/RN-N2/RN-N4", f"signos vitales sin escala aplicable: {r.motivo_no_aplicable}")
        if r.critico:
            self._registrar("RN-D3", f"NEWS2 total={r.total} parámetros críticos={r.motivos}", "Crítico")
        elif r.aplicable and r.hay_signos:
            self._registrar("RN-D3", f"NEWS2 total={r.total} escala SpO2={r.escala_spo2}", "sin cambio")
        return r

    def prioridad(self, detecciones: list[Deteccion], news2: ResultadoNEWS2) -> N:
        propuesta = self.p.clasificacion.nivel_prioridad_propuesto
        final = propuesta
        for d in detecciones:
            self._registrar("RN-D2", f"{d.concepto} por {', '.join(d.vias)}: {d.evidencia}", "hallazgo_critico")
        if detecciones and _ORDEN_PRIORIDAD[final] < _ORDEN_PRIORIDAD[N.CRITICO]:
            final = N.CRITICO
            self._registrar("RN-D8", f"hallazgos críticos {[d.concepto for d in detecciones]}", N.CRITICO.value, propuesta.value)
        if news2.critico and _ORDEN_PRIORIDAD[final] < _ORDEN_PRIORIDAD[N.CRITICO]:
            final = N.CRITICO
            self._registrar("RN-D8", f"NEWS2 crítico ({news2.motivos})", N.CRITICO.value, propuesta.value)
        triage = (self.p.condiciones.triage_urgencias or "").strip().upper()
        if triage in ("I", "II", "1", "2"):
            if self.pack.urgencias.triage_eleva_prioridad and _ORDEN_PRIORIDAD[final] < _ORDEN_PRIORIDAD[N.URGENTE]:
                final = N.URGENTE
                self._registrar("RN-CO16", f"triage {triage}", N.URGENTE.value, propuesta.value)
            else:
                self._registrar("RN-CO16", f"triage {triage} declarado; regla por confirmar", "sin cambio")
        if self.ctx.prioridad_humana is not None and self.ctx.prioridad_humana is not final:
            # RN-J5: una persona puede subir libremente; bajar un Crítico ya exigió rol clínico y justificación.
            self._registrar("RN-J5", f"prioridad fijada por {self.ctx.usuario_humano}", self.ctx.prioridad_humana.value, final.value)
            final = self.ctx.prioridad_humana
        return final

    # --- orquestación ---------------------------------------------------------------

    def evaluar(self) -> Evaluado:
        e = self.p.extraccion
        self.clasificacion()
        identidad = self.identidad()
        self.campos_obligatorios(identidad)
        detecciones = detectar_hallazgos(
            diagnosticos=e.diagnosticos, texto=self.ctx.texto or "", declarados=e.hallazgos_criticos_detectados, pack=self.pack
        )
        self.confianzas(detecciones)
        medicamentos = self.medicamentos()
        fecha = self.fecha()
        news2 = self.news2()
        prioridad = self.prioridad(detecciones, news2)

        tipo_doc = TipoDocumentoPaciente(identidad.tipo) if identidad.tipo in TipoDocumentoPaciente.__members__ else TipoDocumentoPaciente.AUSENTE
        paciente = Paciente(
            nombre=e.paciente.nombre, edad=e.paciente.edad, sexo=e.paciente.sexo,
            documento=DocumentoPaciente(tipo=tipo_doc, valor=identidad.valor_normalizado or identidad.identificador_temporal, estado=identidad.estado),
        )
        profesional = Profesional(
            nombre=e.profesional.nombre, registro_profesional=e.profesional.registro_profesional,
            tipo_documento=e.profesional.tipo_documento, numero_documento=e.profesional.numero_documento,
            jurisdiccion="no_aplica" if not self.pack.identidad_profesional.exige_jurisdiccion else "requerida",
        )
        sv = e.signos_vitales
        signos = SignosVitales(FR=sv.FR, SpO2=sv.SpO2, FC=sv.FC, PAS=sv.PAS, Temp=sv.Temp, nivel_conciencia=sv.nivel_conciencia, NEWS2_total=news2.total)
        c = self.p.clasificacion
        clasificacion = Clasificacion(
            tipo=c.tipo, setting=c.setting, especialidad=c.especialidad, dominio=c.dominio,
            score_confianza=c.score_confianza, nivel_prioridad=prioridad,
        )
        motivos = sorted(self.motivos, key=_SEVERIDAD.index)
        return Evaluado(
            clasificacion=clasificacion,
            prioridad_propuesta=c.nivel_prioridad_propuesto,
            paciente=paciente,
            profesional=profesional,
            fecha_documento=fecha,
            signos_vitales=signos,
            diagnosticos=[Diagnostico(texto=d.texto, cie10_sugerido=d.cie10_sugerido, cie11_sugerido=d.cie11_sugerido) for d in e.diagnosticos],
            procedimientos=[Procedimiento(texto=p.texto, cups=p.cups) for p in e.procedimientos],
            medicamentos=medicamentos,
            hallazgos=[d.concepto for d in detecciones],
            detecciones=detecciones,
            news2=news2,
            identidad=identidad,
            cobertura=self.ctx.cobertura_request or e.cobertura_detectada,
            justificacion_clinica=e.justificacion_clinica,
            motivos=motivos,
            campos_dudosos=self.dudosos,
            historial=self.historial,
        )


def evaluar(propuesta: PropuestaLLM, contexto: ContextoEvaluacion, pack: PackPais, umbrales: Umbrales) -> Evaluado:
    return _Evaluador(propuesta, contexto, pack, umbrales).evaluar()
