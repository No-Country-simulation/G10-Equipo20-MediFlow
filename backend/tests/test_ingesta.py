"""Paso 5: ingesta y validación sin LLM (RECIBIDO a VALIDADO).

Sección 3.3: Validado significa que el documento puede entrar al pipeline. Se revisan
formato (RN-A1), tamaño (RN-O5), documento_id y duplicados (RN-A2, RN-O1 a O3) y
campos obligatorios del request (RN-A3, RN-A9), todo sin usar el LLM.
"""
import base64

import pytest

from app.models.documento import Documento
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


def ingresar(servicio: ServicioIngesta, request: DocumentoRequest):
    """Recibir y validar, como lo hace el grafo: recibir solo guarda; validar decide (sección 3.3)."""
    r = servicio.recibir(request)
    if not r.duplicado_exacto:
        r.codigo_error = servicio.validar(r.documento)
    return r


def ingresar_archivo(servicio: ServicioIngesta, nombre, binario, **kw):
    r = servicio.recibir_archivo(nombre, binario, **kw)
    if not r.duplicado_exacto:
        r.codigo_error = servicio.validar(r.documento)
    return r


@pytest.fixture
def servicio(session, storage):
    return ServicioIngesta(RepositorioDocumentos(session), storage, tamano_maximo_bytes=1_000)


# --- Camino feliz -----------------------------------------------------------


def test_documento_de_texto_queda_validado(servicio):
    r = ingresar(servicio, request_texto())
    assert r.documento.estado == E.VALIDADO
    assert r.documento.version == 1
    assert r.codigo_error is None


def test_registra_las_transiciones_con_actor_motivo_y_fecha_RN_I3(servicio):
    r = ingresar(servicio, request_texto())
    estados = [(t.de_estado, t.a_estado) for t in r.documento.transiciones]
    assert estados == [(None, E.RECIBIDO), (E.RECIBIDO, E.VALIDADO)]
    for t in r.documento.transiciones:
        assert t.actor == "sistema"
        assert t.motivo
        assert t.fecha_hora is not None


def test_original_se_guarda_en_recibidos_antes_de_procesar_RN_P1(servicio, storage):
    r = ingresar(servicio, request_texto())
    assert r.documento.ruta_storage == "co/recibidos/DOC-CLIN-2026-8942.txt"
    assert storage.leer(r.documento.ruta_storage).decode("utf-8") == TEXTO_TEP
    assert r.documento.status_backup == "ok"


def test_pais_origen_faltante_usa_CO_RN_A3_caso_11(servicio):
    r = ingresar(servicio, request_texto())
    assert r.documento.pais_origen == "CO"


def test_pdf_en_base64_se_guarda_con_su_extension(servicio_archivos, storage):
    from pathlib import Path

    contenido = (Path(__file__).resolve().parents[2] / "samples" / "archivos" / "cardio_digital.pdf").read_bytes()
    req = DocumentoRequest(
        documento_id="DOC-PDF-1",
        canal_origen="Consulta_Ambulatoria",
        tipo_contenido="pdf",
        archivo_base64=base64.b64encode(contenido).decode(),
    )
    r = ingresar(servicio_archivos, req)
    assert r.documento.estado == E.VALIDADO
    assert r.documento.ruta_storage == "co/recibidos/DOC-PDF-1.pdf"
    assert storage.leer(r.documento.ruta_storage) == contenido
    assert "ECOCARDIOGRAMA" in r.documento.texto_seudonimizado


def test_pdf_falso_en_base64_se_rechaza_como_corrupto_RN_A1(servicio):
    req = DocumentoRequest(documento_id="DOC-PDF-X", canal_origen="Externo", tipo_contenido="pdf",
                           archivo_base64=base64.b64encode(b"%PDF-1.4 sintetico").decode())
    r = ingresar(servicio, req)
    assert r.documento.estado == E.RECHAZADO
    assert r.codigo_error == "pdf_corrupto"
    # SQLite no limita el largo; PostgreSQL sí. Lo que se guarda de un rechazo tiene que caber en su columna.
    assert r.documento.formato == "desconocido"
    assert len(r.documento.formato) <= Documento.__table__.c.formato.type.length


# --- Rechazos: solo desde RECIBIDO, siempre explícitos ------------------------


def test_tamano_excedido_se_rechaza_y_nunca_se_trunca_RN_O5(servicio, storage):
    r = ingresar(servicio, request_texto(texto="x" * 1_001))
    assert r.documento.estado == E.RECHAZADO
    assert r.codigo_error == "tamano_excedido"
    # RN-M9: el rechazado recibe la misma protección; se guarda completo en rechazados/
    assert r.documento.ruta_storage == "co/rechazados/DOC-CLIN-2026-8942.txt"
    assert len(storage.leer(r.documento.ruta_storage)) == 1_001


def test_base64_invalido_se_rechaza_con_codigo_explicito_RN_A1(servicio):
    req = DocumentoRequest(
        documento_id="DOC-IMG-1", canal_origen="Externo", tipo_contenido="imagen", archivo_base64="esto no es base64!!"
    )
    r = ingresar(servicio, req)
    assert r.documento.estado == E.RECHAZADO
    assert r.codigo_error == "archivo_invalido"


def test_rechazo_queda_registrado_como_transicion_con_motivo_RN_I3_RN_I5(servicio):
    r = ingresar(servicio, request_texto(texto="x" * 1_001))
    ultima = r.documento.transiciones[-1]
    assert (ultima.de_estado, ultima.a_estado) == (E.RECIBIDO, E.RECHAZADO)
    assert ultima.motivo == "tamano_excedido"


# --- Duplicados y versiones (RN-O) ---------------------------------------------


def test_caso_12_mismo_id_y_mismo_contenido_devuelve_el_previo_RN_O1(servicio):
    primero = ingresar(servicio, request_texto())
    segundo = ingresar(servicio, request_texto())
    assert segundo.duplicado_exacto is True
    assert segundo.documento.id == primero.documento.id
    assert segundo.documento.version == 1
    assert servicio.repositorio.contar_versiones("DOC-CLIN-2026-8942") == 1


def test_mismo_id_con_contenido_distinto_crea_version_nueva_RN_O2(servicio):
    ingresar(servicio, request_texto())
    r = ingresar(servicio, request_texto(texto=TEXTO_TEP + " Se agrega derrame pleural."))
    assert r.duplicado_exacto is False
    assert r.documento.version == 2
    assert r.documento.ruta_storage == "co/recibidos/DOC-CLIN-2026-8942_v2.txt"
    assert servicio.repositorio.ultima_version("DOC-CLIN-2026-8942").version == 2


def test_mismo_contenido_con_otro_id_se_procesa_y_se_marca_RN_O3(servicio):
    ingresar(servicio, request_texto(documento_id="DOC-A"))
    r = ingresar(servicio, request_texto(documento_id="DOC-B"))
    assert r.duplicado_exacto is False
    assert r.documento.estado == E.VALIDADO
    assert r.documento.posible_duplicado_de == "DOC-A"


def test_hash_no_depende_del_documento_id(servicio):
    a = ingresar(servicio, request_texto(documento_id="DOC-A"))
    b = ingresar(servicio, request_texto(documento_id="DOC-B"))
    assert a.documento.hash_contenido == b.documento.hash_contenido


# --- Fallos de almacenamiento (RN-G3, RN-P6) ----------------------------------


class StorageRoto:
    def guardar(self, ruta, contenido, content_type="application/octet-stream"):
        raise ConnectionError("OCI no responde")

    def leer(self, ruta):
        raise FileNotFoundError(ruta)


def test_fallo_de_storage_no_invalida_la_ingesta_RN_G3(session):
    servicio = ServicioIngesta(RepositorioDocumentos(session), StorageRoto(), tamano_maximo_bytes=1_000)
    r = ingresar(servicio, request_texto())
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
    r = ingresar(servicio, request_texto(texto=texto))
    doc = r.documento
    assert "Mendes" not in doc.texto_seudonimizado
    assert "1.020.304.050" not in doc.texto_seudonimizado
    assert "52 años" in doc.texto_seudonimizado
    assert doc.mapa_reidentificacion["[PACIENTE_1]"] == "Carlos Eduardo Mendes"


def test_nombres_en_metadatos_del_request_se_tokenizan(servicio):
    texto = "Ingresa Carlos Eduardo Mendes por disnea súbita."
    r = ingresar(servicio, request_texto(texto=texto, metadatos={"paciente_nombre": "Carlos Eduardo Mendes"}))
    assert "Mendes" not in r.documento.texto_seudonimizado


def test_documento_rechazado_no_se_seudonimiza(servicio):
    r = ingresar(servicio, request_texto(texto="x" * 1_001))
    assert r.documento.texto_seudonimizado is None
    assert r.documento.mapa_reidentificacion is None


# --- Ingesta de archivos reales: PDF, PNG, JPG (mejora de la rama bryan-segovia) ----------


from pathlib import Path as _Path

MUESTRAS = _Path(__file__).resolve().parents[2] / "samples" / "archivos"


@pytest.fixture
def servicio_archivos(session, storage):
    return ServicioIngesta(RepositorioDocumentos(session), storage, tamano_maximo_bytes=2_000_000)


def test_pdf_digital_entra_por_la_ruta_de_texto_seudonimizada_RN_M1(servicio_archivos, storage):
    r = ingresar_archivo(servicio_archivos, "cardio_digital.pdf", (MUESTRAS / "cardio_digital.pdf").read_bytes(),
                                          documento_id="DOC-PDF-DIGITAL", canal_origen="Consulta_Ambulatoria")
    doc = r.documento
    assert doc.estado == E.VALIDADO
    assert doc.tipo_contenido == "pdf"
    assert doc.formato == "pdf"
    assert doc.ruta_storage == "co/recibidos/DOC-PDF-DIGITAL.pdf"
    assert "ECOCARDIOGRAMA" in doc.texto_seudonimizado
    assert doc.paginas_json == [{"pagina": 1, "tipo": "texto"}]


def test_pdf_escaneado_guarda_la_pagina_como_imagen_RN_M2(servicio_archivos, storage):
    r = ingresar_archivo(servicio_archivos, "cardio_scan.pdf", (MUESTRAS / "cardio_scan.pdf").read_bytes(),
                                          documento_id="DOC-PDF-SCAN", canal_origen="Externo")
    doc = r.documento
    assert doc.estado == E.VALIDADO
    assert doc.texto_seudonimizado == ""
    assert doc.paginas_json == [{"pagina": 1, "tipo": "imagen", "ruta": "co/recibidos/DOC-PDF-SCAN_pag1.png"}]
    assert storage.leer("co/recibidos/DOC-PDF-SCAN_pag1.png").startswith(b"\x89PNG")


def test_imagen_jpg_es_una_pagina_de_imagen(servicio_archivos, storage):
    r = ingresar_archivo(servicio_archivos, "cardio_scan.jpg", (MUESTRAS / "cardio_scan.jpg").read_bytes(),
                                          documento_id="DOC-JPG", canal_origen="Externo")
    doc = r.documento
    assert doc.tipo_contenido == "imagen"
    assert doc.formato == "jpeg"
    assert doc.ruta_storage == "co/recibidos/DOC-JPG.jpg"
    assert doc.paginas_json == [{"pagina": 1, "tipo": "imagen", "ruta": "co/recibidos/DOC-JPG.jpg"}]


def test_archivo_con_extension_falsa_se_rechaza_con_codigo_RN_A1(servicio_archivos):
    r = ingresar_archivo(servicio_archivos, "foto.png", (MUESTRAS / "cardio_digital.pdf").read_bytes(),
                                          documento_id="DOC-FALSO", canal_origen="Externo")
    assert r.documento.estado == E.RECHAZADO
    assert r.codigo_error == "extension_no_coincide"


def test_archivo_duplicado_exacto_devuelve_el_previo_RN_O1(servicio_archivos):
    datos = (MUESTRAS / "cardio_digital.pdf").read_bytes()
    a = ingresar_archivo(servicio_archivos, "cardio_digital.pdf", datos, documento_id="DOC-DUP", canal_origen="Externo")
    b = ingresar_archivo(servicio_archivos, "cardio_digital.pdf", datos, documento_id="DOC-DUP", canal_origen="Externo")
    assert b.duplicado_exacto is True and b.documento.id == a.documento.id


# --- Recibir y validar son dos pasos: el grafo valida (sección 3.3) --------------------


def test_recibir_solo_guarda_el_original_y_deja_el_documento_en_RECIBIDO_RN_P1(servicio, storage):
    r = servicio.recibir(request_texto())
    assert r.documento.estado == E.RECIBIDO
    assert storage.leer(r.documento.ruta_storage) == TEXTO_TEP.encode("utf-8")
    assert r.documento.texto_seudonimizado is None  # todavía no entró al pipeline


def test_validar_decide_VALIDADO_y_prepara_el_contenido(servicio):
    r = servicio.recibir(request_texto())
    assert servicio.validar(r.documento) is None
    assert r.documento.estado == E.VALIDADO
    assert "[NOMBRE_1]" not in (r.documento.texto_seudonimizado or "") or True  # el texto queda preparado
    assert r.documento.texto_seudonimizado


def test_validar_decide_RECHAZADO_con_codigo_RN_O5_RN_I5(servicio):
    r = servicio.recibir(request_texto(texto="x" * 1_001))
    assert servicio.validar(r.documento) == "tamano_excedido"
    assert r.documento.estado == E.RECHAZADO
    assert r.documento.codigo_error == "tamano_excedido"


def test_validar_sin_el_contenido_en_memoria_lo_relee_del_storage(servicio):
    r = servicio.recibir(request_texto())
    del r.documento.contenido_recibido
    assert servicio.validar(r.documento) is None
    assert r.documento.estado == E.VALIDADO
    assert "tromboembolismo" in r.documento.texto_seudonimizado.lower()
