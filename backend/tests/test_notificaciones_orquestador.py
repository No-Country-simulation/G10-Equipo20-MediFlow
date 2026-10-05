"""Orquestador._emitir_alerta ya no solo guarda la notificación: también la entrega
(RN-F1 Crítico -> Slack, RN-F3 Urgente -> correo). Usa un `Notificador` de prueba en vez
de Slack/SMTP reales -- la entrega real ya se prueba en test_notificaciones.py."""
import pytest

from app.core.config import get_settings
from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import DocumentoRequest
from app.services.ingesta import ServicioIngesta
from app.services.llm import ClienteFalso, ServicioExtraccion
from app.services.orquestador import Orquestador
from tests.test_llm import propuesta_caso_1

TEXTO_CRITICO = (
    "Paciente: Carlos Eduardo Mendes, 52 años. Fecha: 03/04/2026.\n"
    "TC de tórax con contraste: tromboembolismo pulmonar agudo bilateral. FR 28, SpO2 88 %, FC 118, PAS 92.\n"
    "Dr. Andrés Rojas, RM 45678."
)
TEXTO_URGENTE = (
    "Paciente: Ana Torres, 60 años. Fecha: 10/04/2026.\n"
    "Angina inestable, sin cambios isquémicos agudos en ECG. FR 20, SpO2 95 %, FC 98, PAS 128.\n"
    "Dra. Lucía Fernández, RM 11223."
)


class NotificadorEspia:
    def __init__(self, falla: bool = False):
        self.slack: list[dict] = []
        self.slack_urgente: list[dict] = []
        self.correos: list[dict] = []
        self.falla = falla

    def enviar_slack(self, *, mensaje, enlace):
        if self.falla:
            raise ConnectionError("Slack no responde")
        self.slack.append({"mensaje": mensaje, "enlace": enlace})

    def enviar_slack_urgente(self, *, mensaje, enlace):
        if self.falla:
            raise ConnectionError("Slack no responde")
        self.slack_urgente.append({"mensaje": mensaje, "enlace": enlace})

    def enviar_correo(self, *, destinatario, mensaje, enlace):
        if self.falla:
            raise ConnectionError("SMTP no responde")
        self.correos.append({"destinatario": destinatario, "mensaje": mensaje, "enlace": enlace})


@pytest.fixture
def repo(session):
    return RepositorioDocumentos(session)


def _orquestador(repo, storage, propuesta, notificador):
    cliente = ClienteFalso([propuesta])
    return Orquestador(repo, storage, ServicioExtraccion(cliente, max_intentos=1, dormir=lambda s: None),
                       notificador=notificador)


def _ingresar(repo, storage, documento_id, texto):
    req = DocumentoRequest(documento_id=documento_id, canal_origen="Guardia_Emergencias",
                           tipo_contenido="texto", contenido_texto=texto)
    return ServicioIngesta(repo, storage).recibir(req).documento


def test_critico_envia_a_slack(repo, storage):
    espia = NotificadorEspia()
    doc = _ingresar(repo, storage, "DOC-NOTIF-1", TEXTO_CRITICO)
    _orquestador(repo, storage, propuesta_caso_1(), espia).procesar(doc)
    assert len(espia.slack) == 1
    assert "DOC-NOTIF-1" in espia.slack[0]["mensaje"]
    assert espia.correos == []


def test_critico_sin_notificador_explicito_no_revienta(repo, storage):
    """Sin SLACK_WEBHOOK_URL en el entorno, `notificador_desde_settings()` da NotificadorNulo:
    el triaje debe completarse igual, solo que nadie recibe el aviso fuera de la base."""
    doc = _ingresar(repo, storage, "DOC-NOTIF-2", TEXTO_CRITICO)
    cliente = ClienteFalso([propuesta_caso_1()])
    orq = Orquestador(repo, storage, ServicioExtraccion(cliente, max_intentos=1, dormir=lambda s: None))
    resultado = orq.procesar(doc)
    assert resultado.estado.value == "ENRUTADO"
    assert repo.alerta_activa(doc) is not None


def test_una_falla_de_slack_no_tumba_el_triaje_RN_P6(repo, storage):
    espia = NotificadorEspia(falla=True)
    doc = _ingresar(repo, storage, "DOC-NOTIF-3", TEXTO_CRITICO)
    resultado = _orquestador(repo, storage, propuesta_caso_1(), espia).procesar(doc)
    assert resultado.estado.value == "ENRUTADO"
    assert repo.alerta_activa(doc) is not None          # la alerta sí quedó registrada


def _propuesta_urgente() -> dict:
    propuesta = propuesta_caso_1()
    propuesta["clasificacion"]["nivel_prioridad_propuesto"] = "Urgente"
    propuesta["extraccion"]["hallazgos_criticos_detectados"] = []
    propuesta["extraccion"]["diagnosticos"] = [{"texto": "Angina inestable", "cie10_sugerido": "I20.0", "cie11_sugerido": None}]
    # Vitales dentro de rango (sin esto, el NEWS2 de los del caso 1 igual daría Crítico -- RN-D8 solo sube).
    propuesta["extraccion"]["signos_vitales"] = {"FR": 20, "SpO2": 95, "FC": 98, "PAS": 128, "Temp": 36.8, "nivel_conciencia": "alerta"}
    return propuesta


def test_urgente_sin_smtp_cae_a_slack_urgente_y_no_crea_alerta_con_acuse(repo, storage, monkeypatch):
    """Política actual del equipo: sin SMTP_HOST configurado, el aviso Urgente se manda
    por Slack (a un segundo webhook) en vez de perderse en silencio."""
    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()
    espia = NotificadorEspia()
    doc = _ingresar(repo, storage, "DOC-NOTIF-4", TEXTO_URGENTE)
    _orquestador(repo, storage, _propuesta_urgente(), espia).procesar(doc)
    assert len(espia.slack_urgente) == 1
    assert "DOC-NOTIF-4" in espia.slack_urgente[0]["mensaje"]
    assert espia.correos == [] and espia.slack == []
    assert repo.alerta_activa(doc) is None              # RN-F3: sin acuse, no es una "alerta" de la tabla
    get_settings.cache_clear()


def test_urgente_con_smtp_configurado_usa_correo(repo, storage, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.resend.com")
    get_settings.cache_clear()
    espia = NotificadorEspia()
    doc = _ingresar(repo, storage, "DOC-NOTIF-5", TEXTO_URGENTE)
    _orquestador(repo, storage, _propuesta_urgente(), espia).procesar(doc)
    assert len(espia.correos) == 1
    assert espia.slack_urgente == [] and espia.slack == []
    monkeypatch.setenv("SMTP_HOST", "")
    get_settings.cache_clear()
