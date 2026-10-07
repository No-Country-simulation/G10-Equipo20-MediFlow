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


# --- contexto histórico o negado (RN-D2): el término cuenta solo si el texto lo presenta como hallazgo de hoy ---------


def test_antecedente_de_TEP_no_es_hallazgo_de_hoy_y_queda_constancia():
    descartes: list[str] = []
    det = detectar_en_texto("Antecedente de tromboembolismo pulmonar en 2019, anticoagulado. Hoy control de rutina, sin disnea.", PACK, descartes)
    assert conceptos(det) == set()
    assert len(descartes) == 1 and descartes[0].startswith("TEP_AGUDO: 'tromboembolismo pulmonar' solo en contexto histórico o negado")


def test_descartado_o_negado_no_alerta_pero_el_hallazgo_vigente_de_la_misma_nota_si():
    descartes: list[str] = []
    texto = ("Se descarta disección aórtica. Niega infarto previo. Sin signos de taponamiento cardíaco. "
             "Angio-TC: tromboembolismo pulmonar agudo bilateral.")
    det = detectar_en_texto(texto, PACK, descartes)
    assert conceptos(det) == {"TEP_AGUDO"}
    assert {d.split(":")[0] for d in descartes} == {"DISECCION_AORTICA", "TAPONAMIENTO_CARDIACO"}


def test_el_mismo_termino_vigente_en_otra_frase_sigue_contando():
    descartes: list[str] = []
    det = detectar_en_texto("Antecedente de taponamiento cardíaco resuelto. Eco de hoy: taponamiento cardíaco con colapso de AD.", PACK, descartes)
    assert conceptos(det) == {"TAPONAMIENTO_CARDIACO"}
    assert descartes == []


def test_sospecha_y_localizacion_anatomica_siguen_siendo_hallazgo():
    assert conceptos(detectar_en_texto("Sospecha de tromboembolismo pulmonar. Se solicita angio-TC urgente.", PACK)) == {"TEP_AGUDO"}
    assert conceptos(detectar_en_texto("ECG: STEMI anterior extenso.", PACK)) == {"IAM_STEMI"}


def test_el_codigo_en_el_texto_no_se_descarta_por_contexto():
    # El código es una vía propia (RN-D2); el contexto solo se evalúa sobre el término.
    assert conceptos(detectar_en_texto("Antecedente: I26.9.", PACK)) == {"TEP_AGUDO"}


def test_detectar_hallazgos_registra_los_descartes_del_texto():
    descartes: list[str] = []
    det = detectar_hallazgos(diagnosticos=[], texto="Niega disección aórtica previa.", declarados=[], pack=PACK, descartes=descartes)
    assert det == [] and len(descartes) == 1
