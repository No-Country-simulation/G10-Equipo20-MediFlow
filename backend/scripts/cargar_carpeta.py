"""Carga masiva de una carpeta de documentos a MediFlow.

Uso:
    python -m scripts.cargar_carpeta "C:/ruta/FM" --canal Consulta_Ambulatoria --cobertura contributivo
    python -m scripts.cargar_carpeta "C:/ruta/EPICRISIS" --canal Hospitalizado --url http://localhost:8000

El documento_id sale del nombre del archivo (RN-A2). Volver a cargar la misma carpeta
no reprocesa: la API devuelve el resultado previo (RN-O1).
"""
import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

EXTENSIONES = {".pdf", ".png", ".jpg", ".jpeg"}
MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def documento_id_desde_nombre(nombre: str) -> str:
    base = Path(nombre).stem
    # FM-2023-0014 · EPICRISIS-2026-006_Descripcion -> EPICRISIS-2026-006
    coincidencia = re.match(r"^([A-Za-z]+-\d{4}-\d{3,})", base)
    if coincidencia:
        return coincidencia.group(1).upper()
    return re.sub(r"[^A-Z0-9]+", "-", base.upper()).strip("-")[:64]


def cargar_carpeta(carpeta: Path, *, canal_origen: str, cobertura: str | None, enviar: Callable, pais: str = "CO") -> list[dict]:
    """Envía cada archivo soportado de la carpeta. `enviar(ruta, campos, archivo)` devuelve una respuesta con .status_code y .json()."""
    resumen: list[dict] = []
    for archivo in sorted(p for p in Path(carpeta).iterdir() if p.suffix.lower() in EXTENSIONES):
        campos = {"documento_id": documento_id_desde_nombre(archivo.name), "canal_origen": canal_origen, "pais_origen": pais}
        if cobertura:
            campos["cobertura_paciente"] = cobertura
        respuesta = enviar("/documentos/archivo", campos, (archivo.name, archivo.read_bytes(), MIME[archivo.suffix.lower()]))
        try:
            cuerpo = respuesta.json()
        except ValueError:
            cuerpo = {}
        resumen.append({
            "archivo": archivo.name,
            "documento_id": cuerpo.get("documento_id", campos["documento_id"]),
            "http": respuesta.status_code,
            "estado": cuerpo.get("estado"),
            "nivel_prioridad": cuerpo.get("nivel_prioridad"),
            "motivo": (cuerpo.get("resultado") or {}).get("evaluacion", {}).get("motivo_auditoria"),
            "codigo_error": cuerpo.get("codigo_error"),
            "duplicado": bool(cuerpo.get("duplicado")),
        })
        print(f"{archivo.name:55} {respuesta.status_code} {cuerpo.get('estado', '?'):20} {cuerpo.get('nivel_prioridad') or '-':8} {cuerpo.get('codigo_error') or ''}", flush=True)
    return resumen


def _enviar_http(url_base: str) -> Callable:
    import httpx  # noqa: PLC0415

    cliente = httpx.Client(base_url=url_base, timeout=180)

    def enviar(ruta: str, campos: dict, archivo: tuple):
        return cliente.post(ruta, data=campos, files={"archivo": archivo})

    return enviar


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga una carpeta de documentos a MediFlow")
    parser.add_argument("carpeta")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--canal", default="Consulta_Ambulatoria", choices=["Guardia_Emergencias", "Consulta_Ambulatoria", "Hospitalizado", "Externo"])
    parser.add_argument("--cobertura", default=None)
    parser.add_argument("--pais", default="CO")
    parser.add_argument("--json", dest="salida_json", default=None, help="ruta donde guardar el resumen en JSON")
    args = parser.parse_args(argv)
    resumen = cargar_carpeta(Path(args.carpeta), canal_origen=args.canal, cobertura=args.cobertura, pais=args.pais, enviar=_enviar_http(args.url))
    if args.salida_json:
        Path(args.salida_json).write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8")
    por_estado: dict[str, int] = {}
    for r in resumen:
        por_estado[str(r["estado"])] = por_estado.get(str(r["estado"]), 0) + 1
    print(f"\n{len(resumen)} archivos · {por_estado}")
    return 0 if all(r["http"] in (200, 202) for r in resumen) else 1


if __name__ == "__main__":
    sys.exit(main())
