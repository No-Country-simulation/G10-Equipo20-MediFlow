"""Borra del almacenamiento los archivos de este sistema que superaron una antigüedad.

Pensado para los documentos sintéticos de pruebas y demostraciones, que no deben quedar para siempre
en un bucket compartido. Solo alcanza la carpeta propia de este sistema (R2_PREFIJO).

Uso:
    python -m scripts.purgar_storage --dias 30                 # muestra qué borraría, sin borrar
    python -m scripts.purgar_storage --dias 30 --confirmar     # borra
    python -m scripts.purgar_storage --dias 0 --prefijo co/rechazados --confirmar

RN-M5: nunca corre solo ni se programa. Una historia clínica real tiene retención legal (15 años en
Colombia); decidir qué se purga es de una persona, y por eso sin --confirmar no se borra nada.
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

from app.services.storage import ObjetoGuardado, Storage


def vencidos(storage: Storage, *, dias: int, prefijo: str = "", ahora: datetime | None = None,
             protegidas: set[str] | None = None) -> list[ObjetoGuardado]:
    """Objetos cuya última modificación es anterior al límite, del más antiguo al más reciente. Las rutas protegidas
    (las de documentos que todavía no cerraron) nunca entran, por viejas que sean."""
    if dias < 0:
        raise ValueError("--dias no puede ser negativo")
    limite = (ahora or datetime.now(timezone.utc)) - timedelta(days=dias)
    antiguos = [o for o in storage.listar(prefijo) if _con_zona(o.modificado) <= limite and o.ruta not in (protegidas or set())]
    return sorted(antiguos, key=lambda o: _con_zona(o.modificado))


def rutas_protegidas(session) -> set[str]:
    """RN-P1, RN-I4: el original, las páginas y el JSON de un documento que no está en estado final siguen en uso
    (revisión, entrega pendiente, acuse pendiente). Borrarlos dejaría al revisor sin nada que mirar."""
    from sqlalchemy import select  # noqa: PLC0415 - solo cuando se ejecuta contra la base

    from app.models.documento import Documento  # noqa: PLC0415
    from app.services.ciclo_vida import ESTADOS_FINALES  # noqa: PLC0415

    finales = {e.value for e in ESTADOS_FINALES}
    rutas: set[str] = set()
    for doc in session.scalars(select(Documento).where(Documento.estado.not_in(finales))):
        if doc.ruta_storage:
            rutas.add(doc.ruta_storage)
        for pagina in doc.paginas_json or []:
            if pagina.get("ruta"):
                rutas.add(pagina["ruta"])
        ruta_json = (doc.resultado_json or {}).get("ruta_storage")
        if ruta_json:
            rutas.add(ruta_json)
    return rutas


def purgar(storage: Storage, *, dias: int, prefijo: str = "", confirmar: bool = False, ahora: datetime | None = None,
           protegidas: set[str] | None = None) -> list[ObjetoGuardado]:
    """Devuelve lo vencido y, solo con `confirmar`, lo borra."""
    objetos = vencidos(storage, dias=dias, prefijo=prefijo, ahora=ahora, protegidas=protegidas)
    if confirmar:
        for objeto in objetos:
            storage.borrar(objeto.ruta)
    return objetos


def _con_zona(fecha: datetime) -> datetime:
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Purga manual del almacenamiento de MediFlow")
    parser.add_argument("--dias", type=int, required=True, help="borra lo modificado hace más de estos días")
    parser.add_argument("--prefijo", default="", help="carpeta dentro del almacenamiento, por ejemplo co/rechazados")
    parser.add_argument("--confirmar", action="store_true", help="sin esta opción solo se muestra qué se borraría")
    opciones = parser.parse_args()

    from sqlalchemy.orm import Session  # noqa: PLC0415 - lee la configuración solo al ejecutarse

    from app.api.deps import get_storage  # noqa: PLC0415
    from app.core.database import get_engine  # noqa: PLC0415

    with Session(get_engine()) as session:
        protegidas = rutas_protegidas(session)
    print(f"Protegidos (documentos sin cerrar): {len(protegidas)} archivos; no se tocan.")
    objetos = purgar(get_storage(), dias=opciones.dias, prefijo=opciones.prefijo, confirmar=opciones.confirmar, protegidas=protegidas)
    for objeto in objetos:
        print(f"{_con_zona(objeto.modificado):%Y-%m-%d %H:%M}  {objeto.tamano:>10} B  {objeto.ruta}")
    total = sum(o.tamano for o in objetos)
    verbo = "Borrados" if opciones.confirmar else "Se borrarían"
    print(f"{verbo}: {len(objetos)} archivos, {total} bytes." + ("" if opciones.confirmar else " Repite con --confirmar para borrar."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
