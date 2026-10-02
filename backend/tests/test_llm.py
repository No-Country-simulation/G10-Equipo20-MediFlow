"""Paso 7: nodo LLM con salida estructurada.

El LLM propone (clasificación, extracción y prioridad sugerida); el código decide
(RN-D8). Una respuesta fuera de esquema es un fallo, no se corrige adivinando (RN-P3).
Los reintentos son limitados y con espera creciente (RN-P2). Se registran modelo,
versión del prompt y tokens por documento (RN-R5, RN-T3). Al LLM va solo el texto
seudonimizado necesario, nunca el mapa (RN-M1, RN-M3).
"""
import os

import pytest

from app.schemas.propuesta import PropuestaLLM
from app.services.llm import (
    ClienteFalso,
    EntradaLLM,
    ErrorTransitorioLLM,
    FalloLLM,
    RespuestaFueraDeEsquema,
    ServicioExtraccion,
    cargar_prompt,
    esquema_json_estricto,
)

TEXTO_TOKENIZADO = (
    "Paciente: [PACIENTE_1], 52 años. CC [ID_1]. Fecha: [FECHA_1].\n"
    "TC de tórax: tromboembolismo pulmonar agudo bilateral. FR 28, SpO2 88 %, FC 118, PAS 92."
)


def propuesta_caso_1() -> dict:
    return {
        "clasificacion": {
            "tipo": "Informe de Imágenes",
            "setting": "urgencia",
            "especialidad": "Radiología",
            "dominio": "Neumología",
            "rol_autor": "radiólogo",
            "score_confianza": 0.97,
            "nivel_prioridad_propuesto": "Crítico",
        },
        "extraccion": {
            "paciente": {
                "nombre": "[PACIENTE_1]",
                "edad": 52,
                "sexo": None,
                "documento": {"tipo": "CC", "valor": "[ID_1]"},
            },
            "profesional": {"nombre": "[PROFESIONAL_1]", "registro_profesional": "RM 45678", "tipo_documento": None, "numero_documento": None},
            "fecha_documento": "[FECHA_1]",
            "signos_vitales": {"FR": 28, "SpO2": 88, "FC": 118, "PAS": 92, "Temp": None, "nivel_conciencia": "alerta"},
            "diagnosticos": [{"texto": "Tromboembolismo pulmonar agudo", "cie10_sugerido": "I26.9", "cie11_sugerido": "BB00.0"}],
            "procedimientos": [{"texto": "TC de tórax con contraste", "cups": None}],
            "medicamentos": [],
            "hallazgos_criticos_detectados": ["TEP_AGUDO"],
            "cobertura_detectada": None,
            "justificacion_clinica": "Disnea súbita, taquicardia, hipoxemia; TC confirma TEP bilateral.",
        },
        "condiciones": {
            "epoc_hipercapnico": False,
            "embarazo": False,
            "menor_de_16": False,
            "recetario_oficial": None,
            "triage_urgencias": None,
            "porcentaje_ilegible": 0.0,
        },
        "confianzas": {
            "identidad_paciente": 0.96,
            "medicamento_dosis": None,
            "diagnostico_codigo": 0.95,
            "profesional": 0.9,
        },
        "campos_dudosos": [],
    }


# --- Esquema de la propuesta ----------------------------------------------------


def test_propuesta_valida_se_parsea():
    p = PropuestaLLM.model_validate(propuesta_caso_1())
    assert p.clasificacion.nivel_prioridad_propuesto == "Crítico"
    assert p.extraccion.hallazgos_criticos_detectados == ["TEP_AGUDO"]


def test_el_LLM_no_calcula_NEWS2_ni_enruta_RN_D5_RN_D8():
    campos = PropuestaLLM.model_json_schema()["$defs"]
    assert "NEWS2_total" not in str(campos["SignosVitalesPropuestos"]["properties"])
    assert "enrutamiento" not in PropuestaLLM.model_fields
    assert "notificacion_generada" not in PropuestaLLM.model_fields


def test_esquema_estricto_para_openai():
    esquema = esquema_json_estricto(PropuestaLLM)

    def recorrer(nodo):
        if isinstance(nodo, dict):
            if nodo.get("type") == "object":
                assert nodo.get("additionalProperties") is False
                assert set(nodo.get("required", [])) == set(nodo.get("properties", {}).keys())
            for clave in ("default", "minimum", "maximum", "title"):
                assert clave not in nodo
            for v in nodo.values():
                recorrer(v)
        elif isinstance(nodo, list):
            for v in nodo:
                recorrer(v)

    recorrer(esquema)


# --- Prompt -----------------------------------------------------------------------


def test_prompt_se_carga_con_version():
    prompt = cargar_prompt()
    assert prompt.version.startswith("triaje_v")
    assert "MediFlow" in prompt.texto
    assert "Pack Colombia" in prompt.texto or "RN-CO" in prompt.texto


def test_prompt_no_pide_al_LLM_calcular_NEWS2_ni_decidir_rutas():
    texto = cargar_prompt().texto.lower()
    assert "calcula mentalmente" not in texto
    assert "no calcules" in texto or "no calcula" in texto


# --- Servicio de extracción --------------------------------------------------------


@pytest.fixture
def entrada():
    return EntradaLLM(documento_id="DOC-CLIN-2026-8942", texto=TEXTO_TOKENIZADO, canal_origen="Guardia_Emergencias", pais="CO")


def test_devuelve_propuesta_con_metadatos_de_trazabilidad_RN_R5_RN_T3(entrada):
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()], tokens=(1200, 350), modelo="modelo-falso")
    r = ServicioExtraccion(cliente).procesar(entrada)
    assert isinstance(r.propuesta, PropuestaLLM)
    assert r.modelo == "modelo-falso"
    assert r.version_prompt.startswith("triaje_v")
    assert (r.tokens_entrada, r.tokens_salida) == (1200, 350)
    assert r.intentos == 1


def test_al_LLM_solo_va_el_texto_seudonimizado_y_el_contexto_minimo_RN_M1_RN_M3(entrada):
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()])
    ServicioExtraccion(cliente).procesar(entrada)
    llamada = cliente.llamadas[0]
    assert TEXTO_TOKENIZADO in llamada.texto_usuario
    assert "Guardia_Emergencias" in llamada.texto_usuario
    assert "mapa" not in llamada.texto_usuario.lower()
    assert "Mendes" not in llamada.texto_usuario
    assert llamada.esquema["name"] == "PropuestaLLM"


def test_respuesta_fuera_de_esquema_es_fallo_sin_reintento_RN_P3(entrada):
    cliente = ClienteFalso(respuestas=[{"clasificacion": {"tipo": "Receta Médica"}}, propuesta_caso_1()])
    with pytest.raises(RespuestaFueraDeEsquema):
        ServicioExtraccion(cliente).procesar(entrada)
    assert len(cliente.llamadas) == 1


def test_error_transitorio_se_reintenta_con_espera_creciente_RN_P2(entrada):
    esperas = []
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("429"), ErrorTransitorioLLM("timeout"), propuesta_caso_1()])
    servicio = ServicioExtraccion(cliente, max_intentos=3, espera_base_s=0.5, dormir=esperas.append)
    r = servicio.procesar(entrada)
    assert r.intentos == 3
    assert esperas == [0.5, 1.0]


def test_reintentos_agotados_es_fallo_RN_P2(entrada):
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("caído")] * 3)
    servicio = ServicioExtraccion(cliente, max_intentos=3, espera_base_s=0, dormir=lambda s: None)
    with pytest.raises(FalloLLM):
        servicio.procesar(entrada)
    assert len(cliente.llamadas) == 3


class Reloj:
    """Reloj inyectable: cada llamada al LLM y cada espera consumen el tiempo que se les asigne."""

    def __init__(self):
        self.ahora = 0.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


def test_el_tiempo_maximo_por_documento_corta_los_reintentos_RN_P5(entrada):
    reloj = Reloj()
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("timeout")] * 5)
    # Cada intento tarda 50 s. El tercero arranca a los 102 s, dentro del máximo de 120 s, y termina fuera:
    # cuenta como fallo y no hay cuarto intento aunque queden intentos permitidos.
    cliente_lento = type("Lento", (), {"completar_estructurado": lambda self, llamada: (reloj.avanzar(50), cliente.completar_estructurado(llamada))[1]})()
    servicio = ServicioExtraccion(cliente_lento, max_intentos=5, espera_base_s=1, dormir=reloj.avanzar, tiempo_maximo_s=120, reloj=reloj)
    with pytest.raises(FalloLLM, match="RN-P5"):
        servicio.procesar(entrada)
    assert len(cliente.llamadas) == 3


def test_una_respuesta_que_llega_fuera_del_tiempo_maximo_cuenta_como_fallo_RN_P5(entrada):
    reloj = Reloj()
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()])
    cliente_lento = type("Lento", (), {"completar_estructurado": lambda self, llamada: (reloj.avanzar(130), cliente.completar_estructurado(llamada))[1]})()
    servicio = ServicioExtraccion(cliente_lento, max_intentos=3, espera_base_s=0, dormir=lambda s: None, tiempo_maximo_s=120, reloj=reloj)
    with pytest.raises(FalloLLM, match="RN-P5"):
        servicio.procesar(entrada)


def test_dentro_del_tiempo_maximo_los_reintentos_siguen_como_siempre_RN_P2_RN_P5(entrada):
    reloj = Reloj()
    cliente = ClienteFalso(respuestas=[ErrorTransitorioLLM("429"), propuesta_caso_1()])
    servicio = ServicioExtraccion(cliente, max_intentos=3, espera_base_s=1, dormir=reloj.avanzar, tiempo_maximo_s=120, reloj=reloj)
    assert servicio.procesar(entrada).intentos == 2


def test_imagenes_van_como_partes_de_imagen_en_orden_RN_M2():
    entrada = EntradaLLM(documento_id="DOC-IMG", texto="", imagenes=[("aGVsbG8=", "image/png"), ("bW9u", "image/jpeg")], canal_origen="Externo", pais="CO")
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()])
    ServicioExtraccion(cliente).procesar(entrada)
    assert cliente.llamadas[0].imagenes == [("aGVsbG8=", "image/png"), ("bW9u", "image/jpeg")]
    assert "imagen" in cliente.llamadas[0].texto_usuario.lower()


def test_texto_e_imagenes_juntos_para_un_pdf_mixto():
    entrada = EntradaLLM(documento_id="DOC-MIX", texto="Página 1 con texto.", imagenes=[("aGVsbG8=", "image/png")], canal_origen="Externo", pais="CO")
    cliente = ClienteFalso(respuestas=[propuesta_caso_1()])
    ServicioExtraccion(cliente).procesar(entrada)
    assert "Página 1 con texto." in cliente.llamadas[0].texto_usuario
    assert len(cliente.llamadas[0].imagenes) == 1


def test_cliente_gemini_se_construye_sin_llamar_a_la_red():
    from app.services.llm import ClienteGemini

    c = ClienteGemini(api_key="clave-prueba", modelo="gemini-prueba")
    assert c.modelo == "gemini-prueba"


@pytest.mark.integracion
@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="sin GEMINI_API_KEY")
def test_gemini_devuelve_una_propuesta_valida(entrada):
    from app.services.llm import ClienteGemini

    r = ServicioExtraccion(ClienteGemini()).procesar(entrada)
    assert "TEP_AGUDO" in r.propuesta.extraccion.hallazgos_criticos_detectados


# --- Integración real (requiere OPENAI_API_KEY; no bloquea la suite, RN-U4) ------------


@pytest.mark.integracion
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="sin OPENAI_API_KEY")
def test_openai_devuelve_una_propuesta_valida(entrada):
    from app.services.llm import ClienteOpenAI

    r = ServicioExtraccion(ClienteOpenAI()).procesar(entrada)
    assert r.propuesta.clasificacion.tipo == "Informe de Imágenes"
    assert "TEP_AGUDO" in r.propuesta.extraccion.hallazgos_criticos_detectados
