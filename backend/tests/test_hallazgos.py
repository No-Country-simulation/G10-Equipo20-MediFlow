"""Paso 8: hallazgos críticos por concepto, detectados por tres vías (RN-D1, RN-D2, RN-CO6, RN-P4)."""
from app.packs.loader import cargar_pack
from app.schemas.propuesta import DiagnosticoPropuesto as Dx
from app.services.hallazgos import detectar_en_texto, detectar_hallazgos

PACK = cargar_pack("CO")


def conceptos(detecciones):
    return {d.concepto for d in detecciones}


def test_caso_9_codigo_I26_9_detecta_TEP_aunque_el_LLM_no_lo_declare():
    det = detectar_hallazgos(diagnosticos=[Dx(texto="Hallazgo", cie10_sugerido="I26.9")], texto="", declarados=[], pack=PACK)
    assert conceptos(det) == {"TEP_AGUDO"}
    assert det[0].via == "codigo"
    assert "I26.9" in det[0].evidencia


def test_caso_10_codigo_CIE11_BB00_0_detecta_TEP_RN_CO6():
    det = detectar_hallazgos(diagnosticos=[Dx(texto="x", cie11_sugerido="BB00.0")], texto="", declarados=[], pack=PACK)
    assert conceptos(det) == {"TEP_AGUDO"}


def test_termino_textual_con_sinonimo_y_sin_tildes():
    det = detectar_en_texto("Se observa TROMBOEMBOLIA PULMONAR bilateral con sobrecarga de VD.", PACK)
    assert conceptos(det) == {"TEP_AGUDO"}
    assert det[0].via == "termino"


def test_codigo_dentro_del_texto_sin_LLM_RN_P4():
    det = detectar_en_texto("Dx egreso: I21.0 infarto. Control en 7 días.", PACK)
    assert conceptos(det) == {"IAM_STEMI"}


def test_hallazgo_declarado_por_el_LLM_cuenta_como_via_propia():
    det = detectar_hallazgos(diagnosticos=[], texto="", declarados=["EDEMA_AGUDO_PULMON"], pack=PACK)
    assert conceptos(det) == {"EDEMA_AGUDO_PULMON"}
    assert det[0].via == "hallazgo_llm"


def test_concepto_declarado_que_no_existe_se_ignora():
    det = detectar_hallazgos(diagnosticos=[], texto="", declarados=["GRIPA_GRAVE"], pack=PACK)
    assert det == []


def test_neumotorax_por_codigo_exige_signos_de_tension_RN_D1():
    sin = detectar_hallazgos(diagnosticos=[Dx(texto="neumotórax", cie10_sugerido="J93.0")], texto="Neumotórax apical pequeño.", declarados=[], pack=PACK)
    assert sin == []
    con = detectar_hallazgos(diagnosticos=[Dx(texto="neumotórax", cie10_sugerido="J93.0")], texto="Neumotórax a tensión con desviación mediastinal.", declarados=[], pack=PACK)
    assert conceptos(con) == {"NEUMOTORAX_TENSION"}


def test_varias_vias_no_duplican_el_concepto():
    det = detectar_hallazgos(
        diagnosticos=[Dx(texto="TEP agudo", cie10_sugerido="I26.9")],
        texto="tromboembolismo pulmonar agudo",
        declarados=["TEP_AGUDO"],
        pack=PACK,
    )
    assert [d.concepto for d in det].count("TEP_AGUDO") == 1
    assert {"codigo", "termino", "hallazgo_llm"} <= set(det[0].vias)


def test_texto_sin_hallazgos():
    assert detectar_en_texto("Control de hipertensión arterial, buena adherencia.", PACK) == []


def test_codigo_con_formato_libre_se_normaliza():
    det = detectar_hallazgos(diagnosticos=[Dx(texto="x", cie10_sugerido="i26.0")], texto="", declarados=[], pack=PACK)
    assert conceptos(det) == {"TEP_AGUDO"}
