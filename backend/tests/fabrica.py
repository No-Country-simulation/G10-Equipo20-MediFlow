"""Constructores de propuestas del LLM para los tests de evaluación y enrutamiento."""
from app.schemas.propuesta import PropuestaLLM
from app.services.evaluacion import ContextoEvaluacion


def propuesta(**cambios) -> PropuestaLLM:
    """Informe de imágenes de un paciente de 52 años sin identificador, rutina por defecto.

    Las claves de `cambios` son rutas con puntos: "extraccion.paciente.edad".
    """
    base = {
        "clasificacion": {
            "tipo": "Informe de Imágenes", "setting": "urgencia", "especialidad": "Radiología",
            "dominio": "Neumología", "rol_autor": "radiólogo", "score_confianza": 0.97,
            "nivel_prioridad_propuesto": "Rutina",
        },
        "extraccion": {
            "paciente": {"nombre": "Carlos Eduardo Mendes", "edad": 52, "sexo": "M", "documento": {"tipo": None, "valor": None}},
            "profesional": {"nombre": "Andrés Rojas", "registro_profesional": "RM 45678", "tipo_documento": "CC", "numero_documento": "80197268"},
            "fecha_documento": "03/04/2026",
            "signos_vitales": {"FR": 16, "SpO2": 97, "FC": 72, "PAS": 120, "Temp": 36.8, "nivel_conciencia": "alerta"},
            "diagnosticos": [{"texto": "Hipertensión arterial", "cie10_sugerido": "I10", "cie11_sugerido": None}],
            "procedimientos": [{"texto": "TC de tórax", "cups": "879111"}],
            "medicamentos": [],
            "hallazgos_criticos_detectados": [],
            "cobertura_detectada": None,
            "justificacion_clinica": "Disnea",
        },
        "condiciones": {"epoc_hipercapnico": False, "embarazo": False, "menor_de_16": False,
                        "recetario_oficial": None, "triage_urgencias": None, "porcentaje_ilegible": 0.0},
        "confianzas": {"identidad_paciente": 0.98, "medicamento_dosis": None, "diagnostico_codigo": 0.95, "profesional": 0.9},
        "campos_dudosos": [],
    }
    for ruta, valor in cambios.items():
        nodo = base
        partes = ruta.split(".")
        for parte in partes[:-1]:
            nodo = nodo[parte]
        nodo[partes[-1]] = valor
    return PropuestaLLM.model_validate(base)


def receta(medicamentos, **cambios) -> PropuestaLLM:
    base = {
        "clasificacion.tipo": "Receta Médica", "clasificacion.setting": "ambulatorio",
        "clasificacion.especialidad": "Cardiología", "clasificacion.dominio": "Cardiología",
        "extraccion.paciente.documento": {"tipo": "CC", "valor": "1020304050"},
        "extraccion.signos_vitales": {"FR": None, "SpO2": None, "FC": None, "PAS": None, "Temp": None, "nivel_conciencia": None},
        "extraccion.medicamentos": medicamentos,
        "confianzas.medicamento_dosis": 0.97,
    }
    base.update(cambios)
    return propuesta(**base)


def orden(procedimiento="Cateterismo cardíaco", cups="372100", justificacion="Angina de esfuerzo, ECG con infradesnivel, troponina negativa", **cambios) -> PropuestaLLM:
    base = {
        "clasificacion.tipo": "Orden de Procedimiento", "clasificacion.setting": "ambulatorio",
        "clasificacion.especialidad": "Cardiología", "clasificacion.dominio": "Cardiología",
        "extraccion.paciente.documento": {"tipo": "CC", "valor": "1020304050"},
        "extraccion.signos_vitales": {"FR": None, "SpO2": None, "FC": None, "PAS": None, "Temp": None, "nivel_conciencia": None},
        "extraccion.procedimientos": [{"texto": procedimiento, "cups": cups}],
        "extraccion.diagnosticos": [{"texto": "Angina estable", "cie10_sugerido": "I20.8", "cie11_sugerido": None}],
        "extraccion.justificacion_clinica": justificacion,
    }
    base.update(cambios)
    return propuesta(**base)


def tep(**cambios) -> PropuestaLLM:
    """Caso 1 del brief: TC de tórax con TEP, sin identificador."""
    base = {
        "clasificacion.nivel_prioridad_propuesto": "Crítico",
        "extraccion.diagnosticos": [{"texto": "Tromboembolismo pulmonar agudo", "cie10_sugerido": "I26.9", "cie11_sugerido": "BB00.0"}],
        "extraccion.hallazgos_criticos_detectados": ["TEP_AGUDO"],
        "extraccion.signos_vitales": {"FR": 28, "SpO2": 88, "FC": 118, "PAS": 92, "Temp": 37.1, "nivel_conciencia": "alerta"},
    }
    base.update(cambios)
    return propuesta(**base)


def med(dci="losartan", **campos) -> dict:
    m = {"dci": dci, "dosis": "50 mg", "concentracion": "50 mg", "forma_farmaceutica": "tableta", "via": "oral",
         "frecuencia": "cada 24 h", "duracion": "30 días", "cantidad_numeros": "30", "cantidad_letras": "treinta"}
    m.update(campos)
    return m


def ctx(**cambios) -> ContextoEvaluacion:
    base = {"canal_origen": "Consulta_Ambulatoria", "pais": "CO", "cobertura_request": None,
            "texto": "Losartán 50 mg cada 24 h. Control en 30 días."}
    base.update(cambios)
    return ContextoEvaluacion(**base)
