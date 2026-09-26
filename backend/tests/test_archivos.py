"""Mejora traída de la rama bryan-segovia: validación de archivos por contenido y lectura de PDF.

RN-A1: formatos aceptados PDF, JPG, PNG y texto. Se valida el contenido real, no la extensión.
RN-M1/RN-M2: las páginas con texto embebido van por la ruta de texto (seudonimizada); solo las
páginas escaneadas van como imagen al LLM.
"""
from pathlib import Path

import pytest

from app.services.archivos import ArchivoInvalido, leer_pdf, renderizar_pagina, validar_archivo

MUESTRAS = Path(__file__).resolve().parents[2] / "samples" / "archivos"


def muestra(nombre: str) -> bytes:
    return (MUESTRAS / nombre).read_bytes()


# --- Validación por contenido ------------------------------------------------------


@pytest.mark.parametrize("nombre, formato", [("cardio_digital.pdf", "pdf"), ("cardio_scan.png", "png"), ("cardio_scan.jpg", "jpeg")])
def test_acepta_pdf_png_y_jpg_validos_RN_A1(nombre, formato):
    r = validar_archivo(nombre, muestra(nombre))
    assert r.formato == formato


def test_nombre_con_ruta_se_reduce_al_nombre_base():
    r = validar_archivo("C:\\Users\\x\\..\\cardio_digital.pdf", muestra("cardio_digital.pdf"))
    assert r.nombre == "cardio_digital.pdf"


@pytest.mark.parametrize("nombre", ["informe.docx", "informe", "informe.exe"])
def test_extension_no_soportada_RN_A1(nombre):
    with pytest.raises(ArchivoInvalido) as e:
        validar_archivo(nombre, b"%PDF-1.4 x")
    assert e.value.codigo == "formato_no_soportado"


def test_extension_que_no_coincide_con_el_contenido():
    with pytest.raises(ArchivoInvalido) as e:
        validar_archivo("foto.png", muestra("cardio_digital.pdf"))
    assert e.value.codigo == "extension_no_coincide"


def test_archivo_vacio():
    with pytest.raises(ArchivoInvalido) as e:
        validar_archivo("x.pdf", b"")
    assert e.value.codigo == "archivo_vacio"


def test_pdf_corrupto():
    with pytest.raises(ArchivoInvalido) as e:
        validar_archivo("x.pdf", b"%PDF-1.4\ngarbage sin estructura")
    assert e.value.codigo == "pdf_corrupto"


def test_imagen_truncada():
    datos = muestra("cardio_scan.png")[:2000]
    with pytest.raises(ArchivoInvalido) as e:
        validar_archivo("x.png", datos)
    assert e.value.codigo == "imagen_corrupta"


def test_contenido_que_no_es_documento():
    with pytest.raises(ArchivoInvalido) as e:
        validar_archivo("x.pdf", b"hola mundo esto no es un pdf")
    assert e.value.codigo == "contenido_no_reconocido"


# --- Lectura de PDF -------------------------------------------------------------------


def test_pdf_digital_entrega_texto_y_ninguna_pagina_escaneada():
    lectura = leer_pdf(muestra("cardio_digital.pdf"))
    assert lectura.num_paginas == 1
    assert "ECOCARDIOGRAMA" in lectura.texto
    assert lectura.paginas_imagen == []
    assert lectura.paginas_texto == [1]


def test_pdf_escaneado_entrega_una_imagen_png_por_pagina():
    lectura = leer_pdf(muestra("cardio_scan.pdf"))
    assert lectura.texto == ""
    assert lectura.paginas_texto == []
    assert [n for n, _ in lectura.paginas_imagen] == [1]
    assert lectura.paginas_imagen[0][1].startswith(b"\x89PNG")


def test_pdf_mixto_separa_texto_de_escaneo():
    lectura = leer_pdf(muestra("cardio_mixed.pdf"))
    assert lectura.num_paginas == 2
    assert lectura.paginas_texto == [1]
    assert [n for n, _ in lectura.paginas_imagen] == [2]
    assert "ECOCARDIOGRAMA" in lectura.texto


def test_pdf_con_demasiadas_paginas_se_rechaza_RN_O5():
    with pytest.raises(ArchivoInvalido) as e:
        leer_pdf(muestra("cardio_mixed.pdf"), max_paginas=1)
    assert e.value.codigo == "limite_paginas"


def test_renderizar_pagina_devuelve_png():
    png = renderizar_pagina(muestra("cardio_digital.pdf"), 1)
    assert png.startswith(b"\x89PNG")
    with pytest.raises(ArchivoInvalido) as e:
        renderizar_pagina(muestra("cardio_digital.pdf"), 2)
    assert e.value.codigo == "pagina_no_encontrada"
