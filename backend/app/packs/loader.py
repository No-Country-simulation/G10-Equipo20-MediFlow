"""Carga del pack de país y de los umbrales desde archivos de configuración.

Sección 4: agregar un país cuesta un archivo de configuración y cero líneas de lógica.
Sección 7: los umbrales configurables viven en un archivo, no en el código.
"""
from functools import lru_cache
from pathlib import Path

import yaml

from app.packs.modelos import PackPais, Umbrales

DIRECTORIO_CONFIG = Path(__file__).resolve().parents[2] / "config"


def _leer_yaml(ruta: Path) -> dict:
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el archivo de configuración: {ruta}")
    with ruta.open(encoding="utf-8") as archivo:
        return yaml.safe_load(archivo) or {}


@lru_cache
def cargar_pack(codigo_pais: str) -> PackPais:
    """RN-S2: si el pack no existe, el error es explícito (el llamador decide si usa el Genérico)."""
    ruta = DIRECTORIO_CONFIG / "packs" / f"{codigo_pais.lower()}.yaml"
    return PackPais.model_validate(_leer_yaml(ruta))


@lru_cache
def cargar_umbrales() -> Umbrales:
    return Umbrales.model_validate(_leer_yaml(DIRECTORIO_CONFIG / "umbrales.yaml"))
