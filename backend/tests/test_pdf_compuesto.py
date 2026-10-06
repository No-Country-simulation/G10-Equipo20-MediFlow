"""RN-O4: un PDF compuesto se divide en sub-documentos con documento_padre. Cada uno se clasifica y enruta
aparte, y la prioridad del padre es la máxima de los hijos.

El corte lo declara quien envía (páginas por documento) o lo detecta el sistema por los títulos del
vocabulario del pack. El PDF compuesto se arma aquí mismo: no hay muestra en samples/.
"""
from pathlib import Path

import pymupdf
import pytest

from app.packs.loader import cargar_pack
from app.services.archivos import ArchivoInvalido, contar_paginas
from app.services.division import parsear_rangos, segmentar_por_titulos, tipo_por_titulo, titulos_por_tipo
from tests.test_aceptacion import med, receta, TEXTO_RECETA
from tests.test_llm import propuesta_caso_1

MUESTRAS = Path(__file__).resolve().parents[2] / "samples" / "archivos"
TEXTO_EPICRISIS = ("Paciente: Carlos Eduardo Mendes, 52 años. CC 80.123.456. Fecha: 03/04/2026. "
                   "TC de tórax: tromboembolismo pulmonar agudo. FR 28, SpO2 88 %. Dr. Andrés Rojas, RM 45678.")


def pdf_con_paginas(*paginas: str) -> bytes:
    documento = pymupdf.open()
    for texto in paginas:
        pagina = documento.new_page()
        pagina.insert_text((40, 60), texto, fontsize=10)
    return documento.tobytes()


def pdf_compuesto() -> bytes:
    """Página 1: fórmula médica. Páginas 2 y 3: una epicrisis cuya segunda página no repite el título."""
    return pdf_con_paginas(
        "Clínica Cardiopulmonar\nFÓRMULA MÉDICA\n" + TEXTO_RECETA,
        "Clínica Cardiopulmonar\nEPICRISIS\n" + TEXTO_EPICRISIS,
        "Continuación de la epicrisis. Plan: anticoagulación, control en 7 días. Sin otros hallazgos relevantes en el examen.",
    )


def subir(client, documento_id, pdf, **datos):
    return client.post("/documentos/archivo", data={"documento_id": documento_id, "canal_origen": "Consulta_Ambulatoria", **datos},
                       files={"archivo": (f"{documento_id}.pdf", pdf, "application/pdf")})


# --- reglas puras -----------------------------------------------------------------------------------


def test_los_titulos_salen_del_vocabulario_del_pack_y_solo_de_los_tipos_de_documento():
    titulos = titulos_por_tipo(cargar_pack("CO").vocabulario)
    assert {"Receta Médica", "Epicrisis o Alta", "Orden de Procedimiento", "Certificado Médico"} <= set(titulos)
    assert "Registro del profesional" not in titulos and "Asegurador" not in titulos
    assert tipo_por_titulo("Clínica X\nFÓRMULA MÉDICA\nPaciente...", titulos) == "Receta Médica"
    assert tipo_por_titulo("MediFlow IPS      EPICRISIS", titulos) == "Epicrisis o Alta"  # membrete y título en la misma línea
    assert tipo_por_titulo("Se receta losartán.\nmás texto", titulos) is None  # la palabra dentro de una frase no es un título
    assert tipo_por_titulo("Fórmula médica\nPaciente...", titulos) == "Receta Médica"  # en minúsculas, pero encabeza la línea
    assert tipo_por_titulo("Paciente: Ana\nFecha: 03/04/2026\nORDEN DE SERVICIOS", titulos) is None  # el título no está en las dos primeras líneas


def test_una_pagina_sin_titulo_o_escaneada_sigue_con_el_documento_en_curso():
    titulos = titulos_por_tipo(cargar_pack("CO").vocabulario)
    textos = {1: "FÓRMULA MÉDICA\n...", 2: "EPICRISIS\n...", 3: "continuación sin título", 5: "EPICRISIS\nsegunda hoja"}
    assert segmentar_por_titulos(5, textos, titulos) == [[1], [2, 3, 4, 5]]  # la 4 es escaneada; la 5 repite el tipo
    assert segmentar_por_titulos(2, {1: "EPICRISIS", 2: "EPICRISIS"}, titulos) == [[1, 2]]
    assert segmentar_por_titulos(2, {1: "texto sin título", 2: "ORDEN DE SERVICIOS"}, titulos) == [[1], [2]]
    assert segmentar_por_titulos(3, {}, titulos) == [[1, 2, 3]]


@pytest.mark.parametrize("texto, esperado", [("1-2,3", [[1, 2], [3]]), ("1, 2 - 3", [[1], [2, 3]]), ("1,2,3", [[1], [2], [3]])])
def test_las_paginas_declaradas_se_leen_como_rangos(texto, esperado):
    assert parsear_rangos(texto, 3) == esperado


@pytest.mark.parametrize("texto", ["1-3", "1-2", "2-3,1", "1,3", "1-2,2-3", "1-2,3-4", "a-b", "", "1-2,"])
def test_una_division_que_no_cubre_todas_las_paginas_en_orden_y_en_dos_o_mas_partes_es_invalida(texto):
    with pytest.raises(ArchivoInvalido) as error:
        parsear_rangos(texto, 3)
    assert error.value.codigo == "division_invalida"


# --- por la API --------------------------------------------------------------------------------------


def test_RN_O4_el_pdf_compuesto_se_divide_por_titulos_y_cada_parte_se_enruta_aparte(client, llm_falso):
    llm_falso.respuestas.extend([receta([med("losartan", "50 mg")]), propuesta_caso_1()])
    r = subir(client, "DOC-COMP", pdf_compuesto())
    assert r.status_code == 200, r.text
    padre = r.json()
    assert padre["estado"] == "VALIDADO" and padre["num_paginas"] == 3 and padre["documento_padre"] is None
    hijos = padre["sub_documentos"]
    assert [h["documento_id"] for h in hijos] == ["DOC-COMP-1", "DOC-COMP-2"]
    assert [h["documento_padre"] for h in hijos] == ["DOC-COMP", "DOC-COMP"]
    assert [h["num_paginas"] for h in hijos] == [1, 2]
    assert [h["estado"] for h in hijos] == ["ENRUTADO", "ENRUTADO"]
    assert [h["tipo"] for h in hijos] == ["Receta Médica", "Informe de Imágenes"]
    assert [h["nivel_prioridad"] for h in hijos] == ["Rutina", "Crítico"]
    assert padre["nivel_prioridad"] == "Crítico"  # la máxima de los hijos
    # cada hijo fue al LLM con su propio texto
    assert len(llm_falso.llamadas) == 2
    assert "FÓRMULA MÉDICA" in llm_falso.llamadas[0].texto_usuario and "EPICRISIS" not in llm_falso.llamadas[0].texto_usuario
    assert "EPICRISIS" in llm_falso.llamadas[1].texto_usuario and "Continuación" in llm_falso.llamadas[1].texto_usuario
    # el padre explica la división en su historial y no entra al grafo
    detalle = client.get("/documentos/DOC-COMP").json()
    assert "RN-O4" in detalle["transiciones"][-1]["motivo"] and "1, 2-3" in detalle["transiciones"][-1]["motivo"]
    assert detalle["resultado"] is None and [h["documento_id"] for h in detalle["sub_documentos"]] == ["DOC-COMP-1", "DOC-COMP-2"]
    # el original de cada hijo son solo sus páginas
    hijo = client.get("/documentos/DOC-COMP-2").json()
    assert hijo["documento_padre"] == "DOC-COMP" and "sub_documentos" not in hijo
    assert contar_paginas(client.get("/documentos/DOC-COMP-2/original").content) == 2
    assert contar_paginas(client.get("/documentos/DOC-COMP/original").content) == 3
    # la alerta crítica es del hijo, con su propio id
    assert [a["documento_id"] for a in client.get("/alertas").json()] == ["DOC-COMP-2"]


def test_la_division_declarada_manda_sobre_los_titulos_y_una_invalida_rechaza_el_padre(client, llm_falso):
    sin_titulos = pdf_con_paginas("Primera hoja: control de rutina, sin hallazgos. Fecha: 03/04/2026. Firma el profesional tratante.",
                                  "Segunda hoja: otro control de rutina, sin hallazgos. Fecha: 04/04/2026. Firma el profesional tratante.")
    r = subir(client, "DOC-MAL", sin_titulos, paginas_por_documento="1-3")
    assert r.status_code == 400 and r.json()["codigo_error"] == "division_invalida"
    assert client.get("/documentos/DOC-MAL").json()["estado"] == "RECHAZADO"

    llm_falso.respuestas.extend([propuesta_caso_1(), propuesta_caso_1()])
    r = subir(client, "DOC-DECL", sin_titulos, paginas_por_documento="1,2")
    assert r.status_code == 200, r.text
    assert [h["documento_id"] for h in r.json()["sub_documentos"]] == ["DOC-DECL-1", "DOC-DECL-2"]
    assert len(llm_falso.llamadas) == 2


def test_un_pdf_de_varias_paginas_de_un_solo_tipo_no_se_divide(client, llm_falso):
    llm_falso.respuestas.append(propuesta_caso_1())
    r = subir(client, "DOC-EPI", (MUESTRAS / "epicrisis_tep.pdf").read_bytes())  # dos páginas, las dos con el título EPICRISIS
    assert r.status_code == 200, r.text
    assert "sub_documentos" not in r.json() and r.json()["estado"] == "ENRUTADO" and r.json()["num_paginas"] == 2
    assert len(llm_falso.llamadas) == 1


def test_RN_O1_el_mismo_compuesto_otra_vez_devuelve_el_resultado_previo_con_sus_partes(client, llm_falso):
    llm_falso.respuestas.extend([receta([med("losartan", "50 mg")]), propuesta_caso_1()])
    pdf = pdf_compuesto()  # los mismos bytes: cada PDF que se arma lleva otro identificador interno
    subir(client, "DOC-COMP", pdf)
    r = subir(client, "DOC-COMP", pdf)
    assert r.status_code == 200 and r.json()["duplicado"] is True
    assert [h["documento_id"] for h in r.json()["sub_documentos"]] == ["DOC-COMP-1", "DOC-COMP-2"]
    assert len(llm_falso.llamadas) == 2  # nada se reprocesó
    assert len(client.get("/alertas").json()) == 1  # ni se volvió a alertar


def test_la_ruta_json_en_base64_tambien_divide(client, llm_falso):
    import base64

    llm_falso.respuestas.extend([receta([med("losartan", "50 mg")]), propuesta_caso_1()])
    r = client.post("/documentos", json={"documento_id": "DOC-B64", "canal_origen": "Externo", "tipo_contenido": "pdf",
                                         "archivo_base64": base64.b64encode(pdf_compuesto()).decode(), "nombre_archivo": "sobre.pdf"})
    assert r.status_code == 200, r.text
    assert [h["nombre_archivo"] for h in r.json()["sub_documentos"]] == ["sobre_1.pdf", "sobre_2.pdf"]
    listado = client.get("/documentos").json()["items"]
    assert {d["documento_id"]: d["documento_padre"] for d in listado} == {"DOC-B64": None, "DOC-B64-1": "DOC-B64", "DOC-B64-2": "DOC-B64"}
