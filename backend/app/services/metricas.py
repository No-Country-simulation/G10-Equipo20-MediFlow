"""Métricas calculadas desde el historial (RN-R1), aviso por tasa de corrección (RN-R4),
versiones por documento (RN-R5) y costo en tokens (RN-T3). Nunca datos del paciente (RN-M4)."""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alerta import Alerta
from app.models.documento import Documento
from app.packs.modelos import Umbrales
from app.schemas.resultado import EstadoDocumento as E, MotivoAuditoria
from app.services.configuracion import CONFIGURABLES, valor_base

_MOTIVOS = {m.value for m in MotivoAuditoria}
_SIN_DECISION = {E.RECIBIDO.value, E.VALIDADO.value, E.CLASIFICADO.value, E.EXTRAIDO.value, E.EVALUADO.value}

# Familia del campo corregido -> umbral de confianza que lo gobierna (sección 7).
_UMBRAL_POR_FAMILIA = (
    ("extraccion.medicamentos", "confianza.medicamento_dosis"),
    ("confianzas.medicamento_dosis", "confianza.medicamento_dosis"),
    ("extraccion.paciente", "confianza.identidad_paciente"),
    ("confianzas.identidad_paciente", "confianza.identidad_paciente"),
    ("extraccion.diagnosticos", "confianza.diagnostico_codigo"),
    ("confianzas.diagnostico_codigo", "confianza.diagnostico_codigo"),
    ("extraccion.profesional", "confianza.profesional"),
    ("confianzas.profesional", "confianza.profesional"),
    ("clasificacion", "confianza.clasificacion"),
    ("extraccion.", "confianza.resto"),
)


def normalizar_campo(campo: str) -> str:
    """extraccion.medicamentos.0.dosis y extraccion.medicamentos[0].dosis -> extraccion.medicamentos.*.dosis"""
    return re.sub(r"(\.\d+|\[\d+\])(?=\.|$)", ".*", campo)


def umbral_relacionado(campo: str) -> str | None:
    if campo == "nivel_prioridad":
        return None
    for prefijo, umbral in _UMBRAL_POR_FAMILIA:
        if campo.startswith(prefijo):
            return umbral
    return None


def _motivo_de(texto: str) -> str:
    cabeza = texto.split(":", 1)[0].strip()
    return cabeza if cabeza in _MOTIVOS else "otro"


def _paso_por_revision(doc: Documento) -> bool:
    return any(t.a_estado == E.EN_REVISION_HUMANA.value for t in doc.transiciones)


def _redondear(valor: float | None, digitos: int = 3) -> float | None:
    return None if valor is None else round(valor, digitos)


def calcular_metricas(session: Session, umbrales: Umbrales, *, dias: int = 30, ahora: datetime | None = None) -> dict:
    ahora = ahora or datetime.now(timezone.utc)
    desde = ahora - timedelta(days=dias)
    todos = list(session.scalars(select(Documento).order_by(Documento.id)))
    ultimas: dict[str, Documento] = {}
    for d in todos:
        ultimas[d.documento_id] = d  # ordenado por id: la última gana
    documentos = [d for d in ultimas.values() if d.creado_en is None or _aware(d.creado_en) >= desde]
    procesados = [d for d in documentos if d.estado not in _SIN_DECISION]

    # RN-R1: tasa de automatización
    automaticos = [d for d in procesados if not _paso_por_revision(d)]
    tasa_automatizacion = _redondear(len(automaticos) / len(procesados)) if procesados else None

    # RN-R1: porcentaje a revisión por motivo
    por_motivo: Counter[str] = Counter()
    for d in procesados:
        primera = next((t for t in d.transiciones if t.a_estado == E.EN_REVISION_HUMANA.value), None)
        if primera is not None:
            por_motivo[_motivo_de(primera.motivo)] += 1
    revision_por_motivo = {m: {"n": n, "porcentaje": _redondear(n / len(procesados))} for m, n in por_motivo.most_common()}

    # RN-R1: tiempo por etapa
    acumulado: dict[str, list[float]] = defaultdict(list)
    for d in documentos:
        previa = None
        for t in d.transiciones:
            if previa is not None:
                acumulado[f"{previa.a_estado}→{t.a_estado}"].append((_aware(t.fecha_hora) - _aware(previa.fecha_hora)).total_seconds())
            previa = t
    tiempo_por_etapa = {k: round(sum(v) / len(v), 3) for k, v in acumulado.items()}

    # RN-R1: tiempo hasta el acuse en críticos
    plazo = umbrales.tiempos.escalamiento_sin_acuse_min
    alertas = [a for a in session.scalars(select(Alerta)) if _aware(a.emitida_en) >= desde]
    acusadas = [a for a in alertas if a.estado_acuse == "acusado" and a.acusado_en is not None]
    minutos = [(_aware(a.acusado_en) - _aware(a.emitida_en)).total_seconds() / 60 for a in acusadas]
    acuse_criticos = {
        "emitidas": len(alertas),
        "acusadas": len(acusadas),
        "pendientes": len(alertas) - len(acusadas),
        "minutos_promedio": _redondear(sum(minutos) / len(minutos), 2) if minutos else None,
        "dentro_de_plazo": sum(1 for m in minutos if m <= plazo),
        "plazo_min": plazo,
    }

    # RN-R1, RN-R4: tasa de corrección por campo
    revisados = [d for d in procesados if _paso_por_revision(d) and d.propuesta_json]
    docs_por_campo: dict[str, set[str]] = defaultdict(set)
    correcciones_por_campo: Counter[str] = Counter()
    falsos_negativos: list[str] = []
    for d in revisados:
        for c in d.correcciones:
            campo = normalizar_campo(c.campo)
            correcciones_por_campo[campo] += 1
            docs_por_campo[campo].add(d.documento_id)
            if c.campo == "nivel_prioridad" and c.corregido == "Crítico" and c.extraido != "Crítico":
                falsos_negativos.append(d.documento_id)
    limite = umbrales.calidad.limite_correccion_campo
    correccion_por_campo = []
    avisos = []
    for campo, n in correcciones_por_campo.most_common():
        tasa = round(len(docs_por_campo[campo]) / len(revisados), 3) if revisados else 0.0
        umbral = umbral_relacionado(campo)
        supera = tasa > limite
        correccion_por_campo.append({"campo": campo, "correcciones": n, "documentos_revisados": len(revisados), "tasa": tasa,
                                     "umbral_relacionado": umbral, "supera_limite": supera})
        if supera and umbral in CONFIGURABLES:
            actual = valor_base(umbrales, umbral)
            rango = umbrales.rangos.get(umbral)
            propuesto = round(min(actual + 0.02, rango.max if rango else 0.99), 2)
            avisos.append({"regla": "RN-R4", "campo": campo, "tasa": tasa, "limite": limite, "umbral": umbral,
                           "umbral_actual": actual, "umbral_propuesto": propuesto,
                           "propuesta": f"subir {umbral} de {actual} a {propuesto}: la tasa de corrección {tasa:.0%} supera el límite {limite:.0%}"})

    # falsos negativos críticos: los que un humano subió a Crítico
    criticos_totales = sum(1 for d in procesados if d.nivel_prioridad == "Crítico")
    falsos_negativos_criticos = {
        "n": len(falsos_negativos),
        "documentos": falsos_negativos,
        "criticos_totales": criticos_totales,
        "tasa": _redondear(len(falsos_negativos) / criticos_totales) if criticos_totales else None,
    }

    # RN-R5, RN-T3
    versiones = {
        "modelo_llm": dict(Counter(d.modelo_llm for d in documentos if d.modelo_llm)),
        "version_prompt": dict(Counter(d.version_prompt for d in documentos if d.version_prompt)),
        "version_reglas": dict(Counter((d.resultado_json or {}).get("version_reglas") for d in documentos if d.resultado_json)),
        "pack": dict(Counter((d.resultado_json or {}).get("pack_pais") for d in documentos if d.resultado_json)),
    }
    tokens = {"entrada": sum(d.tokens_entrada or 0 for d in documentos), "salida": sum(d.tokens_salida or 0 for d in documentos)}

    return {
        "periodo_dias": dias,
        "calculado_en": ahora.isoformat(),
        "documentos": len(documentos),
        "procesados": len(procesados),
        "por_estado": dict(Counter(d.estado for d in documentos)),
        "por_prioridad": dict(Counter(d.nivel_prioridad for d in documentos if d.nivel_prioridad)),
        "tasa_automatizacion": tasa_automatizacion,
        "revision_por_motivo": revision_por_motivo,
        "tiempo_por_etapa_s": tiempo_por_etapa,
        "acuse_criticos": acuse_criticos,
        "limite_correccion_campo": limite,
        "correccion_por_campo": correccion_por_campo,
        "avisos": avisos,
        "falsos_negativos_criticos": falsos_negativos_criticos,
        "versiones": versiones,
        "tokens": tokens,
    }


def _aware(fecha: datetime) -> datetime:
    """SQLite devuelve fechas sin zona; PostgreSQL con zona. Se comparan todas en UTC."""
    return fecha if fecha.tzinfo is not None else fecha.replace(tzinfo=timezone.utc)
