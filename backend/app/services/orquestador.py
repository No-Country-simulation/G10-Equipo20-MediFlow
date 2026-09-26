"""Orquestación del pipeline sobre un documento ya VALIDADO, y las acciones humanas.

Los nodos del grafo (app/graph) delegan aquí. Toda transición de estado pasa por el
repositorio, que valida el ciclo de vida (RN-I). Toda decisión queda en el historial (RN-G2).
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.graph.estado import EstadoGrafo
from app.models.documento import Documento
from app.packs.loader import cargar_pack, cargar_umbrales
from app.packs.modelos import PackPais, Umbrales
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.propuesta import PropuestaLLM
from app.schemas.resultado import (
    Clasificacion,
    DecisionRegistrada,
    Destino as D,
    Dominio,
    Enrutamiento,
    EstadoDocumento as E,
    Evaluacion,
    Extraccion,
    MotivoAuditoria as M,
    NivelPrioridad as N,
    Notificacion,
    ResultadoTriaje,
    Setting,
    TipoDocumento as T,
)
from app.services.ciclo_vida import prefijo_storage
from app.services.configuracion import ServicioConfiguracion
from app.services.enrutamiento import ContextoEnrutamiento, enrutar
from app.services.errores import ErrorDeRevision
from app.services.evaluacion import ContextoEvaluacion, evaluar
from app.services.hallazgos import detectar_en_texto
from app.services.llm import EntradaLLM, FalloLLM, RespuestaFueraDeEsquema, ServicioExtraccion
from app.services.seudonimizacion import limpiar_tokens_no_resueltos, reidentificar_estructura
from app.services.storage import Storage
from app.services.usuarios import ServicioUsuarios

logger = logging.getLogger(__name__)

ACTOR_SISTEMA = "sistema"
_ORDEN = {N.RUTINA: 0, N.URGENTE: 1, N.CRITICO: 2}
_SETTING_POR_CANAL = {"Guardia_Emergencias": Setting.URGENCIA, "Hospitalizado": Setting.HOSPITALIZADO}
_MIME_POR_EXTENSION = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "pdf": "application/pdf"}
_ROLES_CLINICOS = {"auditor_clinico", "jefe_urgencias"}


__all__ = ["ErrorDeRevision", "Orquestador", "ACTOR_SISTEMA"]


class Orquestador:
    def __init__(
        self,
        repositorio: RepositorioDocumentos,
        storage: Storage,
        extraccion: ServicioExtraccion,
        *,
        pack: PackPais | None = None,
        umbrales: Umbrales | None = None,
        url_base: str | None = None,
    ):
        self.repo = repositorio
        self.storage = storage
        self.extraccion = extraccion
        settings = get_settings()
        # RN-L4: la configuración vigente (base + versión activa) rige lo que se procesa desde ahora.
        configuracion = ServicioConfiguracion(repositorio.session) if pack is None or umbrales is None else None
        self.pack = pack or configuracion.pack(settings.pais_instalacion)
        self.umbrales = umbrales or configuracion.umbrales()
        self.usuarios = ServicioUsuarios(repositorio.session)
        self.url_base = url_base or settings.url_base_documentos
        self.version_reglas = settings.version_reglas
        from app.graph.grafo import construir_grafo  # noqa: PLC0415 - evita import circular

        self._grafo = construir_grafo(self)

    # --- entrada principal -----------------------------------------------------------

    def procesar(self, documento: Documento) -> ResultadoTriaje:
        if documento.estado != E.VALIDADO:
            raise ValueError(f"solo se procesa un documento VALIDADO; está en {documento.estado}")
        final = self._grafo.invoke({"documento_pk": documento.id})
        return final["resultado"]

    def _doc(self, estado: EstadoGrafo) -> Documento:
        return self.repo.session.get(Documento, estado["documento_pk"])

    # --- nodos del grafo -----------------------------------------------------------------

    def nodo_clasificar_extraer(self, estado: EstadoGrafo) -> EstadoGrafo:
        doc = self._doc(estado)
        try:
            entrada = self._entrada_llm(doc)
            r = self.extraccion.procesar(entrada)
        except (FalloLLM, RespuestaFueraDeEsquema, FileNotFoundError, OSError) as error:
            motivo = f"fallo_tecnico: {type(error).__name__}: {str(error)[:300]}"
            self.repo.transicionar(doc, E.FALLO_TECNICO, actor=ACTOR_SISTEMA, motivo=motivo)
            return {"error": motivo, "propuesta": None}

        doc.modelo_llm, doc.version_prompt = r.modelo, r.version_prompt
        doc.tokens_entrada, doc.tokens_salida = r.tokens_entrada, r.tokens_salida
        c = r.propuesta.clasificacion
        self.repo.transicionar(doc, E.CLASIFICADO, actor=ACTOR_SISTEMA, motivo=f"LLM: {c.tipo.value}, score {c.score_confianza}")
        # Re-identificación local: el JSON final lleva los datos reales; el LLM solo vio tokens (RN-M1).
        propuesta = limpiar_tokens_no_resueltos(reidentificar_estructura(r.propuesta.model_dump(mode="json"), doc.mapa_reidentificacion or {}))
        doc.propuesta_json = propuesta
        self.repo.transicionar(doc, E.EXTRAIDO, actor=ACTOR_SISTEMA, motivo="datos clínicos estructurados y re-identificados")
        return {"propuesta": propuesta, "error": None}

    def nodo_evaluar(self, estado: EstadoGrafo) -> EstadoGrafo:
        doc = self._doc(estado)
        evaluado = evaluar(PropuestaLLM.model_validate(estado["propuesta"]), self._contexto_evaluacion(doc), self.pack, self.umbrales)
        self.repo.transicionar(doc, E.EVALUADO, actor=ACTOR_SISTEMA, motivo=f"prioridad {evaluado.prioridad.value}; motivos {[m.value for m in evaluado.motivos]}")
        return {"evaluado": evaluado}

    def nodo_enrutar(self, estado: EstadoGrafo) -> EstadoGrafo:
        doc = self._doc(estado)
        resultado = enrutar(estado["evaluado"], self._contexto_enrutamiento(doc), self.pack, self.umbrales)
        motivo = resultado.enrutamiento.justificacion_enrutamiento
        if resultado.evaluacion.motivo_auditoria is not None:
            motivo = f"{resultado.evaluacion.motivo_auditoria.value}: {motivo}"
        self.repo.transicionar(doc, resultado.estado, actor=ACTOR_SISTEMA, motivo=motivo[:500])
        self._persistir(doc, resultado)
        return {"resultado": resultado}

    def nodo_fallo_tecnico(self, estado: EstadoGrafo) -> EstadoGrafo:
        """RN-P2: reintentos agotados -> revisión humana. RN-P4: la detección determinística sigue alertando."""
        doc = self._doc(estado)
        texto = doc.texto_seudonimizado or ""
        detecciones = detectar_en_texto(texto, self.pack)
        # RN-P4: solo lo que el sistema no pudo leer (páginas escaneadas) va con prioridad máxima; un PDF con texto se evalúa por su texto.
        es_imagen = any(p.get("tipo") == "imagen" for p in doc.paginas_json or [])
        nivel = N.CRITICO if (detecciones or es_imagen) else N.RUTINA
        historial = [DecisionRegistrada(regla="RN-P2", evidencia=estado.get("error") or "fallo", decision="revision_humana:fallo_tecnico")]
        for d in detecciones:
            historial.append(DecisionRegistrada(regla="RN-P4", evidencia=f"{d.concepto}: {d.evidencia}", decision="alerta sin LLM"))
        if es_imagen:
            historial.append(DecisionRegistrada(regla="RN-P4", evidencia="imagen sin lectura del LLM", decision="revisión humana con prioridad máxima"))

        ruta = f"{prefijo_storage(E.EN_REVISION_HUMANA, doc.pais_origen)}/{doc.documento_id}{self._sufijo(doc)}.json"
        notificacion = None
        if nivel is N.CRITICO:
            notificacion = Notificacion(canal="Slack", destinatario="Jefe de Urgencias",
                                        mensaje=f"Alerta Crítica. Doc: {doc.documento_id}. Nivel: Crítico. Requiere acuse.",
                                        enlace=f"{self.url_base}/{doc.documento_id}")
        resultado = ResultadoTriaje(
            documento_id=doc.documento_id,
            clasificacion=Clasificacion(tipo=T.NO_CLASIFICABLE, setting=_SETTING_POR_CANAL.get(doc.canal_origen, Setting.AMBULATORIO),
                                        especialidad="desconocida", dominio=Dominio.OTRO, score_confianza=0.0, nivel_prioridad=nivel),
            extraccion=Extraccion(hallazgos_criticos_detectados=[d.concepto for d in detecciones]),
            evaluacion=Evaluacion(requiere_auditoria_humana=True, motivo_auditoria=M.FALLO_TECNICO, campos_dudosos=[]),
            enrutamiento=Enrutamiento(destino_principal=D.COLA_REVISION_HUMANA, justificacion_enrutamiento="RN-P2: fallo técnico con reintentos agotados"),
            notificacion_generada=notificacion,
            estado=E.EN_REVISION_HUMANA,
            pack_pais=self.pack.pais,
            version_reglas=self.version_reglas,
            historial_decisiones=historial,
            ruta_storage=ruta,
            posible_duplicado_de=doc.posible_duplicado_de,
        )
        self.repo.transicionar(doc, E.EN_REVISION_HUMANA, actor=ACTOR_SISTEMA, motivo="fallo_tecnico")
        self._persistir(doc, resultado)
        return {"resultado": resultado}

    # --- acciones humanas (RN-J) ---------------------------------------------------------

    def resolver_revision(self, doc: Documento, *, accion: str, usuario: str, rol: str, motivo: str, correcciones: dict[str, Any] | None = None) -> ResultadoTriaje:
        self.usuarios.validar_actor(usuario, "resolver_revision", rol)
        if doc.estado != E.EN_REVISION_HUMANA:
            raise ErrorDeRevision(409, f"RN-I4: el documento está en {doc.estado}, no en revisión humana")
        if not usuario.strip():
            raise ErrorDeRevision(422, "RN-K5: la acción exige un usuario identificado")
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)

        if accion == "rechazar":
            if not motivo.strip():
                raise ErrorDeRevision(422, "RN-J3: rechazar exige motivo")
            self.repo.transicionar(doc, E.RECHAZADO, actor=usuario, motivo=motivo)
            resultado.estado = E.RECHAZADO
            resultado.historial_decisiones.append(DecisionRegistrada(regla="RN-J3", evidencia=f"{usuario} ({rol}): {motivo}", decision="rechazado"))
            self._persistir(doc, resultado, emitir_alerta=False)
            return resultado

        if accion == "aprobar":
            plan = resultado.enrutamiento.destinos_tras_revision
            if not plan:
                raise ErrorDeRevision(409, "no hay plan de enrutamiento; corrija la propuesta con la acción corregir")
            self.repo.transicionar(doc, E.RESUELTO, actor=usuario, motivo=motivo or "aprobado")
            resultado.enrutamiento = resultado.enrutamiento.model_copy(update={
                "destino_principal": plan[0], "destinos_secundarios": plan[1:], "destinos_tras_revision": [],
                "justificacion_enrutamiento": f"aprobado por {usuario} ({rol}); " + resultado.enrutamiento.justificacion_enrutamiento,
            })
            resultado.evaluacion = Evaluacion(requiere_auditoria_humana=False, motivo_auditoria=None, campos_dudosos=resultado.evaluacion.campos_dudosos)
            resultado.estado = E.ENRUTADO
            resultado.ruta_storage = f"{prefijo_storage(E.ENRUTADO, doc.pais_origen, nivel=resultado.clasificacion.nivel_prioridad.value)}/{doc.documento_id}{self._sufijo(doc)}.json"
            resultado.historial_decisiones.append(DecisionRegistrada(regla="RN-J3", evidencia=f"{usuario} ({rol}): {motivo}", decision="aprobado"))
            self.repo.transicionar(doc, E.ENRUTADO, actor=usuario, motivo=motivo or "aprobado")
            self._persistir(doc, resultado, emitir_alerta=False)
            return resultado

        if accion == "corregir":
            return self._corregir(doc, resultado, usuario=usuario, rol=rol, motivo=motivo, correcciones=correcciones or {})

        raise ErrorDeRevision(422, f"acción desconocida: {accion}")

    def _corregir(self, doc: Documento, resultado: ResultadoTriaje, *, usuario: str, rol: str, motivo: str, correcciones: dict[str, Any]) -> ResultadoTriaje:
        if not doc.propuesta_json:
            raise ErrorDeRevision(409, "sin propuesta que corregir (fallo técnico sin lectura del LLM)")
        if not correcciones:
            raise ErrorDeRevision(422, "corregir exige al menos una corrección")
        propuesta = json.loads(json.dumps(doc.propuesta_json))
        prioridad_humana: N | None = None
        for campo, valor in correcciones.items():
            if campo == "nivel_prioridad":
                nueva = N(valor)
                actual = N(doc.nivel_prioridad) if doc.nivel_prioridad else N.RUTINA
                if _ORDEN[nueva] < _ORDEN[actual]:
                    # RN-J5: bajar un Crítico exige rol clínico y justificación escrita.
                    if rol not in _ROLES_CLINICOS:
                        raise ErrorDeRevision(403, "RN-J5: solo un rol clínico puede bajar la prioridad")
                    if not motivo.strip():
                        raise ErrorDeRevision(422, "RN-J5: bajar la prioridad exige justificación escrita")
                prioridad_humana = nueva
                self.repo.registrar_correccion(doc, campo=campo, extraido=doc.nivel_prioridad, corregido=valor, usuario=usuario)
                continue
            anterior = _asignar(propuesta, campo, valor)
            self.repo.registrar_correccion(doc, campo=campo, extraido=anterior, corregido=valor, usuario=usuario)  # RN-J8

        doc.propuesta_json = propuesta
        self.repo.transicionar(doc, E.RESUELTO, actor=usuario, motivo=motivo or "corregido")
        # RN-J4: se re-ejecutan las reglas determinísticas; no se vuelve a llamar al LLM.
        contexto = self._contexto_evaluacion(doc)
        contexto.prioridad_humana = prioridad_humana
        contexto.usuario_humano = usuario
        evaluado = evaluar(PropuestaLLM.model_validate(propuesta), contexto, self.pack, self.umbrales)
        self.repo.transicionar(doc, E.EVALUADO, actor=usuario, motivo=f"RN-J4: reglas re-ejecutadas tras corrección de {list(correcciones)}")
        nuevo = enrutar(evaluado, self._contexto_enrutamiento(doc), self.pack, self.umbrales)
        nuevo.historial_decisiones = resultado.historial_decisiones + [
            DecisionRegistrada(regla="RN-J3", evidencia=f"{usuario} ({rol}) corrigió {list(correcciones)}: {motivo}", decision="corregido")
        ] + nuevo.historial_decisiones
        self.repo.transicionar(doc, nuevo.estado, actor=usuario, motivo=nuevo.enrutamiento.justificacion_enrutamiento[:500])
        self._persistir(doc, nuevo, emitir_alerta=self.repo.alerta_activa(doc) is None)
        return nuevo

    def acusar(self, doc: Documento, usuario: str) -> dict[str, Any]:
        if not usuario.strip():
            raise ErrorDeRevision(422, "RN-Q5: el acuse lo da un usuario identificado")
        self.usuarios.validar_actor(usuario, "acusar_alerta")
        alerta = self.repo.alerta_activa(doc)
        if alerta is None:
            raise ErrorDeRevision(404, "el documento no tiene alerta crítica")
        if alerta.estado_acuse != "acusado":
            self.repo.acusar_alerta(alerta, usuario)
        self._intentar_cierre(doc)
        self.repo.guardar()
        return {"documento_id": doc.documento_id, "estado_acuse": alerta.estado_acuse, "acusado_por": alerta.acusado_por, "estado": doc.estado}

    def entregar(self, doc: Documento, destino: str) -> dict[str, Any]:
        if doc.estado != E.ENRUTADO:
            raise ErrorDeRevision(409, f"solo se confirma la entrega de un documento ENRUTADO; está en {doc.estado}")
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)
        plan = [resultado.enrutamiento.destino_principal.value, *(d.value for d in resultado.enrutamiento.destinos_secundarios)]
        if destino not in plan:
            raise ErrorDeRevision(400, f"{destino} no está en el plan de enrutamiento {plan}")
        entregas = dict(doc.entregas_json or {})
        entregas[destino] = True
        doc.entregas_json = entregas  # la entrega no cambia de estado hasta el cierre (RN-I)
        pendientes = self._intentar_cierre(doc)
        self.repo.guardar()
        return {"documento_id": doc.documento_id, "estado": doc.estado, "entregas": entregas,
                "retenidas": resultado.enrutamiento.entregas_retenidas, "pendientes": pendientes}

    # --- Farmacia (RN-E6, RN-J6, RN-CO9) ---------------------------------------------------

    @staticmethod
    def plan_de(resultado: ResultadoTriaje) -> list[str]:
        return [resultado.enrutamiento.destino_principal.value, *(d.value for d in resultado.enrutamiento.destinos_secundarios)]

    @staticmethod
    def verificaciones_requeridas(resultado: ResultadoTriaje) -> int:
        exige_doble = any(m.alto_riesgo or m.control_especial for m in resultado.extraccion.medicamentos)
        return 2 if exige_doble else 1

    def es_receta_por_verificar(self, doc: Documento) -> bool:
        if doc.estado != E.ENRUTADO or not doc.resultado_json:
            return False
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)
        if resultado.clasificacion.tipo is not T.RECETA or D.FARMACIA_HOSPITALARIA.value not in self.plan_de(resultado):
            return False
        return not (doc.entregas_json or {}).get(D.FARMACIA_HOSPITALARIA.value)

    def verificar_farmacia(self, doc: Documento, usuario: str) -> dict[str, Any]:
        if not usuario.strip():
            raise ErrorDeRevision(422, "RN-K5: la verificación exige un usuario identificado")
        self.usuarios.validar_actor(usuario, "verificar_receta")
        if not self.es_receta_por_verificar(doc):
            raise ErrorDeRevision(409, "solo se verifican recetas enrutadas a Farmacia y aún no verificadas")
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)
        requeridas = self.verificaciones_requeridas(resultado)
        verificaciones = list(doc.verificaciones_json or [])
        if any(v["usuario"] == usuario.strip() for v in verificaciones):
            raise ErrorDeRevision(409, "RN-J6: la segunda verificación requiere otra persona")
        verificaciones.append({"orden": len(verificaciones) + 1, "usuario": usuario.strip(), "fecha_hora": datetime.now(timezone.utc).isoformat()})
        doc.verificaciones_json = verificaciones
        completa = len(verificaciones) >= requeridas
        resultado.historial_decisiones.append(DecisionRegistrada(
            regla="RN-J6" if requeridas == 2 else "RN-E2",
            evidencia=f"verificación {len(verificaciones)}/{requeridas} por {usuario.strip()}",
            decision="farmacia_verificada" if completa else "pendiente_segunda_verificacion",
        ))
        if completa:
            entregas = dict(doc.entregas_json or {})
            entregas[D.FARMACIA_HOSPITALARIA.value] = True
            doc.entregas_json = entregas
        doc.resultado_json = resultado.model_dump(mode="json")
        pendientes = self._intentar_cierre(doc) if completa else []
        self.repo.guardar()
        return {"documento_id": doc.documento_id, "verificaciones": [{"orden": v["orden"], "usuario": v["usuario"]} for v in verificaciones],
                "requeridas": requeridas, "completa": completa, "estado": doc.estado, "pendientes": pendientes}

    # --- Autorizaciones (RN-E5, RN-E9, RN-CO13) ---------------------------------------------

    def es_orden_por_autorizar(self, doc: Documento) -> bool:
        if doc.estado != E.ENRUTADO or not doc.resultado_json or doc.autorizacion_json:
            return False
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)
        return resultado.clasificacion.tipo is T.ORDEN_PROCEDIMIENTO and D.AUDITORIA_AUTORIZACIONES.value in self.plan_de(resultado)

    def resolver_autorizacion(self, doc: Documento, *, accion: str, usuario: str, motivo: str) -> dict[str, Any]:
        if not usuario.strip():
            raise ErrorDeRevision(422, "RN-K5: la acción exige un usuario identificado")
        self.usuarios.validar_actor(usuario, "resolver_autorizacion")
        if accion not in ("aprobar", "devolver"):
            raise ErrorDeRevision(422, f"acción desconocida: {accion}")
        if accion == "devolver" and not motivo.strip():
            raise ErrorDeRevision(422, "RN-E5: devolver al solicitante exige motivo")
        if not self.es_orden_por_autorizar(doc):
            raise ErrorDeRevision(409, "solo se resuelven órdenes enrutadas a Auditoría y aún no resueltas")
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)
        estado = "aprobada" if accion == "aprobar" else "devuelta"
        doc.autorizacion_json = {"estado": estado, "usuario": usuario.strip(), "motivo": motivo.strip(), "fecha_hora": datetime.now(timezone.utc).isoformat()}
        resultado.historial_decisiones.append(DecisionRegistrada(
            regla="RN-E9" if accion == "aprobar" else "RN-E5",
            evidencia=f"{usuario.strip()}: {motivo.strip() or 'sin observaciones'}",
            decision="autorizacion_aprobada" if accion == "aprobar" else "devuelta_al_solicitante",
        ))
        entregas = dict(doc.entregas_json or {})
        entregas[D.AUDITORIA_AUTORIZACIONES.value] = True
        doc.entregas_json = entregas
        doc.resultado_json = resultado.model_dump(mode="json")
        pendientes = self._intentar_cierre(doc)
        self.repo.guardar()
        return {"documento_id": doc.documento_id, "autorizacion": doc.autorizacion_json, "estado": doc.estado, "pendientes": pendientes}

    def _intentar_cierre(self, doc: Documento) -> list[str]:
        """ENRUTADO -> ENTREGADO cuando los destinos no retenidos confirmaron y, si es crítico, hay acuse (RN-J7)."""
        if doc.estado != E.ENRUTADO:
            return []
        resultado = ResultadoTriaje.model_validate(doc.resultado_json)
        plan = [resultado.enrutamiento.destino_principal.value, *(d.value for d in resultado.enrutamiento.destinos_secundarios)]
        entregas = doc.entregas_json or {}
        retenidas = resultado.enrutamiento.entregas_retenidas
        pendientes = [d for d in plan if d not in retenidas and not entregas.get(d)]
        alerta = self.repo.alerta_activa(doc)
        if alerta is not None and alerta.estado_acuse != "acusado":
            pendientes.append("acuse_alerta")
        if not pendientes:
            self.repo.transicionar(doc, E.ENTREGADO, actor=ACTOR_SISTEMA, motivo="destinos confirmados" + ("; alerta con acuse" if alerta else ""))
            resultado.estado = E.ENTREGADO
            doc.resultado_json = resultado.model_dump(mode="json")
        return pendientes

    # --- utilidades ---------------------------------------------------------------------------

    def _sufijo(self, doc: Documento) -> str:
        return f"_v{doc.version}" if doc.version > 1 else ""

    def _entrada_llm(self, doc: Documento) -> EntradaLLM:
        """Texto seudonimizado (RN-M1) más las páginas escaneadas como imágenes (RN-M2), leídas del respaldo (RN-P1)."""
        import base64  # noqa: PLC0415

        imagenes: list[tuple[str, str]] = []
        for pagina in doc.paginas_json or []:
            if pagina.get("tipo") != "imagen":
                continue
            ruta = pagina.get("ruta")
            if not ruta:
                raise FileNotFoundError(f"página {pagina.get('pagina')} sin respaldo; no se puede enviar al LLM")
            extension = ruta.rsplit(".", 1)[-1].lower()
            imagenes.append((base64.b64encode(self.storage.leer(ruta)).decode(), _MIME_POR_EXTENSION.get(extension, "image/png")))
        texto = doc.texto_seudonimizado or ""
        if not texto.strip() and not imagenes:
            raise FileNotFoundError("documento sin texto ni páginas legibles")
        return EntradaLLM(documento_id=doc.documento_id, texto=texto, canal_origen=doc.canal_origen, pais=doc.pais_origen,
                          cobertura=doc.cobertura_paciente, imagenes=imagenes)

    def recalcular(self, doc: Documento, *, pack: PackPais, umbrales: Umbrales) -> ResultadoTriaje:
        """RN-L6: qué decidirían las reglas con otra configuración. No toca el documento ni llama al LLM."""
        evaluado = evaluar(PropuestaLLM.model_validate(doc.propuesta_json), self._contexto_evaluacion(doc), pack, umbrales)
        return enrutar(evaluado, self._contexto_enrutamiento(doc), pack, umbrales)

    def _contexto_evaluacion(self, doc: Documento) -> ContextoEvaluacion:
        return ContextoEvaluacion(canal_origen=doc.canal_origen, pais=doc.pais_origen, cobertura_request=doc.cobertura_paciente,
                                  texto=doc.texto_seudonimizado or "")

    def _contexto_enrutamiento(self, doc: Documento) -> ContextoEnrutamiento:
        return ContextoEnrutamiento(documento_id=doc.documento_id, canal_origen=doc.canal_origen, pais=doc.pais_origen, version=doc.version,
                                    url_base=self.url_base, posible_duplicado_de=doc.posible_duplicado_de, version_reglas=self.version_reglas)

    def _persistir(self, doc: Documento, resultado: ResultadoTriaje, *, emitir_alerta: bool = True) -> None:
        doc.nivel_prioridad = resultado.clasificacion.nivel_prioridad.value
        if emitir_alerta:
            self._emitir_alerta(doc, resultado)
        self._respaldar_json(doc, resultado)
        doc.resultado_json = resultado.model_dump(mode="json")
        self.repo.guardar()

    def _emitir_alerta(self, doc: Documento, resultado: ResultadoTriaje) -> None:
        """RN-F1 con las excepciones RN-O2 (versión sin subir de nivel) y RN-O3 (posible duplicado)."""
        n = resultado.notificacion_generada
        if n is None or resultado.clasificacion.nivel_prioridad is not N.CRITICO or self.repo.alerta_activa(doc) is not None:
            return
        previa = self.repo.version_previa(doc)
        if previa is not None and previa.nivel_prioridad and _ORDEN[N(previa.nivel_prioridad)] >= _ORDEN[N.CRITICO]:
            resultado.historial_decisiones.append(DecisionRegistrada(regla="RN-O2", evidencia=f"versión {previa.version} ya era {previa.nivel_prioridad}", decision="sin nueva alerta"))
            return
        if doc.posible_duplicado_de:
            original = self.repo.alerta_por_documento_id(doc.posible_duplicado_de)
            if original is not None and original.nivel == N.CRITICO.value:
                resultado.historial_decisiones.append(DecisionRegistrada(regla="RN-O3", evidencia=f"posible duplicado de {doc.posible_duplicado_de} con alerta activa", decision="alerta no duplicada"))
                return
        self.repo.crear_alerta(doc, nivel=N.CRITICO.value, canal=n.canal, destinatario=n.destinatario, mensaje=n.mensaje, enlace=n.enlace)

    def _respaldar_json(self, doc: Documento, resultado: ResultadoTriaje) -> None:
        """RN-G2: se guarda el JSON con el historial. RN-G3: un fallo no invalida el triaje."""
        if not resultado.ruta_storage:
            return
        try:
            cuerpo = json.dumps(resultado.model_dump(mode="json"), ensure_ascii=False, indent=2).encode("utf-8")
            self.storage.guardar(resultado.ruta_storage, cuerpo, "application/json")
            resultado.status_backup = "ok"
        except Exception as error:  # noqa: BLE001
            logger.warning("Fallo de respaldo del resultado %s: %s", doc.documento_id, error)  # RN-M4
            resultado.status_backup = "error"


def _asignar(estructura: dict[str, Any], ruta: str, valor: Any) -> Any:
    """Asigna `valor` en una ruta con puntos y devuelve el valor anterior. Soporta índices: medicamentos[0].dosis."""
    partes = [p for p in re.split(r"\.|\[(\d+)\]", ruta) if p]
    nodo: Any = estructura
    for parte in partes[:-1]:
        nodo = nodo[int(parte)] if parte.isdigit() else nodo.setdefault(parte, {})
    ultima = partes[-1]
    clave: Any = int(ultima) if ultima.isdigit() else ultima
    anterior = nodo[clave] if (isinstance(nodo, list) or clave in nodo) else None
    nodo[clave] = valor
    return anterior
