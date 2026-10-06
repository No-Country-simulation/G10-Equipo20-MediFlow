"""Compuerta de calidad (RN-R3): corre las reglas sobre el conjunto de referencia (RN-R2) y dice si hay falsos
negativos críticos nuevos respecto de una línea base.

Uso:
  python -m scripts.compuerta_calidad                                   # reglas vigentes sobre las propuestas guardadas
  python -m scripts.compuerta_calidad --guardar-linea-base base.json    # deja la línea base de hoy
  python -m scripts.compuerta_calidad --linea-base base.json            # sale con 1 si aparece un falso negativo nuevo
  python -m scripts.compuerta_calidad --llm --linea-base base.json      # vuelve a pedir la propuesta al LLM configurado
                                                                        # (modelo y prompt actuales) sobre el texto seudonimizado

Sin --llm no llama a ningún servicio externo. Con --llm cuesta tokens: es una prueba de integración.
"""
import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.services.compuerta import ResultadoCompuerta, comparar, documentos_de, evaluar_conjunto
from app.services.configuracion import ServicioConfiguracion
from app.services.llm import EntradaLLM, ServicioExtraccion


def ejecutar(session: Session, *, linea_base: dict | None = None, llm=None) -> tuple[dict, int]:
    """Devuelve el informe y el código de salida: 1 si hay falsos negativos críticos nuevos frente a la línea base."""
    settings = get_settings()
    configuracion = ServicioConfiguracion(session)
    pack, umbrales = configuracion.pack(settings.pais_instalacion), configuracion.umbrales()
    documentos = documentos_de(configuracion.casos_referencia())
    propuestas = None
    if llm is not None:
        extraccion = ServicioExtraccion(llm, max_intentos=settings.llm_max_intentos)
        propuestas = {}
        for d in documentos:
            if not d.texto.strip():
                continue  # ruta de imagen: el conjunto no guarda las páginas
            r = extraccion.procesar(EntradaLLM(documento_id=d.documento_id, texto=d.texto, canal_origen=d.canal_origen, pais=d.pais))
            propuestas[(d.documento_id, d.version)] = r.propuesta.model_dump(mode="json")
    resultado = evaluar_conjunto(documentos, pack, umbrales, propuestas)
    informe = {"modo": "llm" if llm is not None else "reglas", "modelo": getattr(llm, "modelo", None) if llm is not None else None,
               "version_prompt": settings.prompt_version, **resultado.como_dict()}
    if linea_base is None:
        return informe, 0
    base = ResultadoCompuerta(falsos_negativos=list(linea_base.get("detalle", [])))
    comparacion = comparar(base, resultado)
    informe["linea_base"] = {"falsos_negativos": len(base.falsos_negativos)}
    informe["nuevos_falsos_negativos"] = comparacion["nuevos_falsos_negativos"]
    informe["empeora"] = comparacion["empeora"]
    return informe, 1 if comparacion["empeora"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RN-R3: compuerta de calidad sobre el conjunto de referencia")
    parser.add_argument("--linea-base", type=Path, help="informe previo con el que comparar")
    parser.add_argument("--guardar-linea-base", type=Path, help="escribe el informe de hoy como línea base")
    parser.add_argument("--llm", action="store_true", help="vuelve a pedir cada propuesta al LLM configurado (cuesta tokens)")
    args = parser.parse_args(argv)

    linea_base = json.loads(args.linea_base.read_text(encoding="utf-8")) if args.linea_base else None
    llm = None
    if args.llm:
        from app.api.deps import get_llm  # noqa: PLC0415 - solo cuando se pide

        llm = get_llm()
    with Session(get_engine()) as session:
        informe, codigo = ejecutar(session, linea_base=linea_base, llm=llm)
    if args.guardar_linea_base:
        args.guardar_linea_base.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{informe['documentos']} documentos de referencia evaluados ({informe['modo']}), {informe['sin_propuesta']} sin propuesta; "
          f"{informe['criticos_esperados']} críticos esperados; {informe['falsos_negativos']} falsos negativos críticos")
    for f in informe["detalle"]:
        print(f"  - {f['documento_id']} v{f['version']}: esperado {f['esperado']}, obtenido {f['obtenido']}")
    if linea_base is not None:
        print("EMPEORA: no sale a producción (RN-R3). Nuevos: " + ", ".join(informe["nuevos_falsos_negativos"]) if codigo else
              f"Sin falsos negativos nuevos frente a la línea base ({informe['linea_base']['falsos_negativos']}).")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
