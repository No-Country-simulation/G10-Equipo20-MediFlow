"""Paso 3: contrato de entrada (request) del agente."""
import pytest
from pydantic import ValidationError

from app.schemas.request import CanalOrigen, CoberturaPaciente, DocumentoRequest, TipoContenido


def request_minimo(**cambios) -> dict:
    base = {
        "documento_id": "DOC-CLIN-2026-8942",
        "canal_origen": "Guardia_Emergencias",
        "tipo_contenido": "texto",
        "contenido_texto": "TC de tórax: tromboembolismo pulmonar agudo.",
    }
    base.update(cambios)
    return base


def test_request_minimo_es_valido():
    req = DocumentoRequest(**request_minimo())
    assert req.documento_id == "DOC-CLIN-2026-8942"
    assert req.canal_origen is CanalOrigen.GUARDIA_EMERGENCIAS


def test_documento_id_es_obligatorio_RN_A2():
    datos = request_minimo()
    del datos["documento_id"]
    with pytest.raises(ValidationError):
        DocumentoRequest(**datos)


def test_documento_id_vacio_es_invalido_RN_A2():
    with pytest.raises(ValidationError):
        DocumentoRequest(**request_minimo(documento_id="   "))


def test_canal_origen_es_obligatorio_RN_A9():
    datos = request_minimo()
    del datos["canal_origen"]
    with pytest.raises(ValidationError):
        DocumentoRequest(**datos)


def test_canal_origen_es_lista_cerrada_RN_A9():
    with pytest.raises(ValidationError):
        DocumentoRequest(**request_minimo(canal_origen="Urgencias"))
    assert {c.value for c in CanalOrigen} == {
        "Guardia_Emergencias", "Consulta_Ambulatoria", "Hospitalizado", "Externo",
    }


def test_pais_origen_por_defecto_es_CO_RN_A3_caso_11():
    req = DocumentoRequest(**request_minimo())
    assert req.pais_origen == "CO"


def test_pais_origen_declarado_se_respeta_RN_A3():
    req = DocumentoRequest(**request_minimo(pais_origen="MX"))
    assert req.pais_origen == "MX"


def test_cobertura_paciente_es_opcional_RN_A10():
    assert DocumentoRequest(**request_minimo()).cobertura_paciente is None


def test_cobertura_paciente_valores_pack_CO_RN_CO12():
    assert {c.value for c in CoberturaPaciente} == {
        "contributivo", "subsidiado", "especial_excepcion", "soat", "arl",
        "plan_voluntario", "no_afiliado",
    }
    req = DocumentoRequest(**request_minimo(cobertura_paciente="contributivo"))
    assert req.cobertura_paciente is CoberturaPaciente.CONTRIBUTIVO
    with pytest.raises(ValidationError):
        DocumentoRequest(**request_minimo(cobertura_paciente="prepagada"))


def test_tipo_contenido_es_lista_cerrada_RN_A1():
    assert {t.value for t in TipoContenido} == {"texto", "pdf", "imagen"}
    with pytest.raises(ValidationError):
        DocumentoRequest(**request_minimo(tipo_contenido="docx"))


def test_texto_exige_contenido_texto_RN_A1():
    datos = request_minimo()
    del datos["contenido_texto"]
    with pytest.raises(ValidationError):
        DocumentoRequest(**datos)


def test_pdf_e_imagen_exigen_archivo_base64_RN_A1():
    with pytest.raises(ValidationError):
        DocumentoRequest(**request_minimo(tipo_contenido="pdf", contenido_texto=None))
    req = DocumentoRequest(
        **request_minimo(tipo_contenido="imagen", contenido_texto=None, archivo_base64="aGVsbG8=")
    )
    assert req.archivo_base64 == "aGVsbG8="


def test_campos_extra_del_brief_no_rechazan_el_request_RN_G7():
    req = DocumentoRequest(**request_minimo(origen_sistema="HIS-Legacy"))
    assert req.documento_id == "DOC-CLIN-2026-8942"
