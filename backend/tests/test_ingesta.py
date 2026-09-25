"""Paso 5: ingesta y validación sin LLM (RECIBIDO a VALIDADO).

Sección 3.3: Validado significa que el documento puede entrar al pipeline. Se revisan
formato (RN-A1), tamaño (RN-O5), documento_id y duplicados (RN-A2, RN-O1 a O3) y
campos obligatorios del request (RN-A3, RN-A9), todo sin usar el LLM.
"""
import base64

import pytest

from app.repositories.documentos import RepositorioDocumentos
from app.schemas.request import DocumentoRequest
from app.schemas.resultado import EstadoDocumento as E
from app.services.ingesta import ServicioIngesta
from app.services.storage import StorageLocal

TEXTO_TEP = "TC de tórax: tromboembolismo pulmonar agudo bilateral. Paciente 52 años."


def request_texto(documento_id="DOC-CLIN-2026-8942", texto=TEXTO_TEP, **extra) -> DocumentoRequest:
    return DocumentoRequest(
        documento_id=documento_id,
        canal_origen="Guardia_Emergencias",
        tipo_contenido="texto",
        contenido_texto=texto,
        **extra,
    )


@pytest.fixture
def servicio(session, storage):
    return ServicioIngesta(RepositorioDocumentos(session), storage, tamano_maximo_bytes=1_000)


# --- Camino feliz -----------------------------------------------------------


def test_documento_de_texto_queda_validado(servicio):
    r = servicio.recibir(request_texto())
    assert r.documento.estado == E.VALIDADO
    assert r.documento.version == 1
    assert r.codigo_error is None


def test_registra_las_transiciones_con_actor_motivo_y_fecha_RN_I3(servicio):
    r = servicio.recibir(request_texto())
    estados = [(t.de_estado, t.a_estado) for t in r.documento.transiciones]
    assert estados == [(None, E.RECIBIDO), (E.RECIBIDO, E.VALIDADO)]
    for t in r.documento.transiciones:
        assert t.actor == "sistema"
        assert t.motivo
        assert t.fecha_hora is not None


def test_original_se_guarda_en_recibidos_antes_de_procesar_RN_P1(servicio, storage):
    r = servicio.recibir(request_texto())
    assert r.documento.ruta_storage == "co/recibidos/DOC-CLIN-2026-8942.txt"
    assert storage.leer(r.documento.ruta_storage).decode("utf-8") == TEXTO_TEP
    assert r.documento.status_backup == "ok"


def test_pais_origen_faltante_usa_CO_RN_A3_caso_11(servicio):
    r = servicio.recibir(request_texto())
    assert r.documento.pais_origen == "CO"


def test_pdf_en_base64_se_guarda_con_su_extension(servicio, storage):
    contenido = b"%PDF-1.4 sintetico"
    req = DocumentoRequest(
        documento_id="DOC-PDF-1",
        canal_origen="Consulta_Ambulatoria",
        tipo_contenido="pdf",
        archivo_base64=base64.b64encode(contenido).decode(),
    )
    r = servicio.recibir(req)
    assert r.documento.estado == E.VALIDADO
    assert r.documento.ruta_storage == "co/recibidos/DOC-PDF-1.pdf"
    assert storage.leer(r.documento.ruta_storage) == contenido


# --- Rechazos: solo desde RECIBIDO, siempre explícitos ------------------------


def test_tamano_excedido_se_rechaza_y_nunca_se_trunca_RN_O5(servicio, storage):
    r = servicio.recibir(request_texto(texto="x" * 1_001))
    assert r.documento.estado == E.RECHAZADO
    assert r.codigo_error == "tamano_excedido"
    # RN-M9: el rechazado recibe la misma protección; se guarda completo en rechazados/
    assert r.documento.ruta_storage == "co/rechazados/DOC-CLIN-2026-8942.txt"
    assert len(storage.leer(r.documento.ruta_storage)) == 1_001


def test_base64_invalido_se_rechaza_con_codigo_explicito_RN_A1(servicio):
    req = DocumentoRequest(
        documento_id="DOC-IMG-1", canal_origen="Externo", tipo_contenido="imagen", archivo_base64="esto no es base64!!"
    )
    r = servicio.recibir(req)
    assert r.documento.estado == E.RECHAZADO
    assert r.codigo_error == "archivo_invalido"


def test_rechazo_queda_registrado_como_transicion_con_motivo_RN_I3_RN_I5(servicio):
    r = servicio.recibir(request_texto(texto="x" * 1_001))
    ultima = r.documento.transiciones[-1]
    assert (ultima.de_estado, ultima.a_estado) == (E.RECIBIDO, E.RECHAZADO)
    assert ultima.motivo == "tamano_excedido"


# --- Duplicados y versiones (RN-O) ---------------------------------------------


def test_caso_12_mismo_id_y_mismo_contenido_devuelve_el_previo_RN_O1(servicio):
    primero = servicio.recibir(request_texto())
    segundo = servicio.recibir(request_texto())
    assert segundo.duplicado_exacto is True
    assert segundo.documento.id == primero.documento.id
    assert segundo.documento.version == 1
    assert servicio.repositorio.contar_versiones("DOC-CLIN-2026-8942") == 1


def test_mismo_id_con_contenido_distinto_crea_version_nueva_RN_O2(servicio):
    servicio.recibir(request_texto())
    r = servicio.recibir(request_texto(texto=TEXTO_TEP + " Se agrega derrame pleural."))
    assert r.duplicado_exacto is False
    assert r.documento.version == 2
    assert r.documento.ruta_storage == "co/recibidos/DOC-CLIN-2026-8942_v2.txt"
    assert servicio.repositorio.ultima_version("DOC-CLIN-2026-8942").version == 2


def test_mismo_contenido_con_otro_id_se_procesa_y_se_marca_RN_O3(servicio):
    servicio.recibir(request_texto(documento_id="DOC-A"))
    r = servicio.recibir(request_texto(documento_id="DOC-B"))
    assert r.duplicado_exacto is False
    assert r.documento.estado == E.VALIDADO
    assert r.documento.posible_duplicado_de == "DOC-A"


def test_hash_no_depende_del_documento_id(servicio):
    a = servicio.recibir(request_texto(documento_id="DOC-A"))
    b = servicio.recibir(request_texto(documento_id="DOC-B"))
    assert a.documento.hash_contenido == b.documento.hash_contenido


# --- Fallos de almacenamiento (RN-G3, RN-P6) ----------------------------------


class StorageRoto:
    def guardar(self, ruta, contenido, content_type="application/octet-stream"):
        raise ConnectionError("OCI no responde")

    def leer(self, ruta):
        raise FileNotFoundError(ruta)


def test_fallo_de_storage_no_invalida_la_ingesta_RN_G3(session):
    servicio = ServicioIngesta(RepositorioDocumentos(session), StorageRoto(), tamano_maximo_bytes=1_000)
    r = servicio.recibir(request_texto())
    assert r.documento.estado == E.VALIDADO
    assert r.documento.status_backup == "error"
    assert r.documento.ruta_storage is None


def test_storage_local_escribe_bajo_su_directorio(tmp_path):
    st = StorageLocal(tmp_path)
    st.guardar("co/recibidos/x.txt", b"hola")
    assert (tmp_path / "co" / "recibidos" / "x.txt").read_bytes() == b"hola"
    assert st.leer("co/recibidos/x.txt") == b"hola"
    with pytest.raises(ValueError):
        st.guardar("../fuera.txt", b"no")


# --- Seudonimización en la ruta de texto (RN-M1) ------------------------------


def test_texto_validado_queda_seudonimizado_con_mapa_local_RN_M1(servicio):
    texto = "Paciente: Carlos Eduardo Mendes, 52 años. CC 1.020.304.050. TC: TEP agudo."
    r = servicio.recibir(request_texto(texto=texto))
    doc = r.documento
    assert "Mendes" not in doc.texto_seudonimizado
    assert "1.020.304.050" not in doc.texto_seudonimizado
    assert "52 años" in doc.texto_seudonimizado
    assert doc.mapa_reidentificacion["[PACIENTE_1]"] == "Carlos Eduardo Mendes"


def test_nombres_en_metadatos_del_request_se_tokenizan(servicio):
    texto = "Ingresa Carlos Eduardo Mendes por disnea súbita."
    r = servicio.recibir(request_texto(texto=texto, metadatos={"paciente_nombre": "Carlos Eduardo Mendes"}))
    assert "Mendes" not in r.documento.texto_seudonimizado


def test_documento_rechazado_no_se_seudonimiza(servicio):
    r = servicio.recibir(request_texto(texto="x" * 1_001))
    assert r.documento.texto_seudonimizado is None
    assert r.documento.mapa_reidentificacion is None
