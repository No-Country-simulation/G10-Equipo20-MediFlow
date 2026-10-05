"""Cargador masivo: envía una carpeta de PDF, PNG o JPG a la API (para alimentar el sistema con lotes)."""
from pathlib import Path

from app.services.llm import ErrorTransitorioLLM
from scripts.cargar_carpeta import cargar_carpeta, documento_id_desde_nombre

MUESTRAS = Path(__file__).resolve().parents[2] / "samples" / "archivos"


def test_documento_id_sale_del_nombre_del_archivo():
    assert documento_id_desde_nombre("FM-2023-0014.pdf") == "FM-2023-0014"
    assert documento_id_desde_nombre("EPICRISIS-2026-006_Tromboembolismo_pulmonar.pdf") == "EPICRISIS-2026-006"
    assert documento_id_desde_nombre("cardio scan (1).jpg") == "CARDIO-SCAN-1"


def test_carga_una_carpeta_y_resume_resultados(tmp_path, client, llm_falso):
    carpeta = tmp_path / "lote"
    carpeta.mkdir()
    (carpeta / "FM-2023-0014.pdf").write_bytes((MUESTRAS / "fm_losartan_amlodipino.pdf").read_bytes())
    (carpeta / "EPICRISIS-2026-006.pdf").write_bytes((MUESTRAS / "epicrisis_tep.pdf").read_bytes())
    (carpeta / "notas.txt").write_text("se ignora", encoding="utf-8")
    llm_falso.respuestas.extend([ErrorTransitorioLLM("sin clave")] * 6)

    def enviar(ruta: str, campos: dict, archivo: tuple):
        return client.post(ruta, data=campos, files={"archivo": archivo})

    resumen = cargar_carpeta(carpeta, canal_origen="Consulta_Ambulatoria", cobertura="contributivo", enviar=enviar)
    assert [r["documento_id"] for r in resumen] == ["EPICRISIS-2026-006", "FM-2023-0014"]
    assert all(r["estado"] == "EN_REVISION_HUMANA" for r in resumen)
    assert resumen[0]["nivel_prioridad"] == "Crítico"  # el TEP se detecta sin LLM (RN-P4)
    assert resumen[1]["nivel_prioridad"] == "Rutina"
    # Idempotente: volver a cargar devuelve duplicados sin reprocesar (RN-O1)
    otra = cargar_carpeta(carpeta, canal_origen="Consulta_Ambulatoria", cobertura="contributivo", enviar=enviar)
    assert all(r["duplicado"] for r in otra)
