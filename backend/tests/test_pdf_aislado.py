"""La lectura de PDF corre en un proceso aparte con límite de tiempo (RN-O5, RN-P5): un PDF malformado que
cuelgue o tumbe a pymupdf no tumba la API; el documento se rechaza con un código explícito."""
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import archivos, pdf_aislado
from app.services.archivos import ArchivoInvalido, contar_paginas, extraer_paginas, leer_pdf, renderizar_pagina

MUESTRAS = Path(__file__).resolve().parents[2] / "samples" / "archivos"


def test_el_padre_no_carga_pymupdf_y_el_hijo_responde_las_cuatro_operaciones():
    assert not hasattr(archivos, "pymupdf")  # el módulo que usa la API no abre PDF en su proceso
    pdf = (MUESTRAS / "cardio_mixed.pdf").read_bytes()
    assert contar_paginas(pdf) == 2
    lectura = leer_pdf(pdf)
    assert lectura.num_paginas == 2 and lectura.paginas_texto == [1] and [n for n, _ in lectura.paginas_imagen] == [2]
    assert "ECOCARDIOGRAMA" in lectura.texto and lectura.paginas_imagen[0][1].startswith(b"\x89PNG")
    assert renderizar_pagina(pdf, 2).startswith(b"\x89PNG")
    assert contar_paginas(extraer_paginas(pdf, [2])) == 1


def test_sin_respuesta_a_tiempo_el_pdf_se_rechaza_y_la_api_sigue(monkeypatch):
    pdf = (MUESTRAS / "cardio_digital.pdf").read_bytes()
    with pytest.raises(ArchivoInvalido) as error:
        pdf_aislado.ejecutar("contar", pdf, timeout_s=0.001)  # ni el arranque del hijo cabe en ese plazo
    assert error.value.codigo == "pdf_tiempo_excedido"
    assert contar_paginas(pdf) == 1  # el siguiente PDF se atiende normalmente


def test_si_el_hijo_muere_o_responde_basura_el_pdf_cuenta_como_corrupto(monkeypatch):
    class Muerto:
        returncode = -11
        stdout = b""
        stderr = b"segmentation fault"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Muerto())
    with pytest.raises(ArchivoInvalido) as error:
        leer_pdf(b"%PDF-1.4 lo que sea")
    assert error.value.codigo == "pdf_corrupto"

    class Basura:
        returncode = 0
        stdout = b"\xff\xfe no es json"
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: Basura())
    with pytest.raises(ArchivoInvalido) as error:
        contar_paginas(b"%PDF-1.4 lo que sea")
    assert error.value.codigo == "pdf_corrupto"


def test_los_codigos_del_hijo_llegan_tal_cual():
    pdf = (MUESTRAS / "cardio_mixed.pdf").read_bytes()
    with pytest.raises(ArchivoInvalido) as error:
        leer_pdf(pdf, max_paginas=1)
    assert error.value.codigo == "limite_paginas"
    with pytest.raises(ArchivoInvalido) as error:
        renderizar_pagina(pdf, 9)
    assert error.value.codigo == "pagina_no_encontrada"
    with pytest.raises(ArchivoInvalido) as error:
        extraer_paginas(pdf, [3])
    assert error.value.codigo == "pagina_no_encontrada"
    with pytest.raises(ArchivoInvalido) as error:
        contar_paginas(b"%PDF-1.4 sintetico roto")
    assert error.value.codigo == "pdf_corrupto"
    with pytest.raises(ValueError):
        pdf_aislado.ejecutar("borrar_todo", pdf)


def test_el_hijo_se_puede_invocar_como_programa_y_nunca_imprime_contenido_ante_un_error():
    proceso = subprocess.run([sys.executable, "-m", "app.services.pdf_aislado", '{"operacion": "contar"}'],
                             input=b"no es un pdf", capture_output=True, cwd=pdf_aislado.RAIZ, check=False)
    assert proceso.returncode == 0 and proceso.stdout == b'{"error": "pdf_corrupto"}'
    proceso = subprocess.run([sys.executable, "-m", "app.services.pdf_aislado", "esto no es json"],
                             input=b"", capture_output=True, cwd=pdf_aislado.RAIZ, check=False)
    assert proceso.returncode == 0 and b"pdf_corrupto" in proceso.stdout
