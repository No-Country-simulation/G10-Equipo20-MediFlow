"""Almacenamiento en el bucket R2 que comparte el equipo (RN-G1, RN-P1) y purga manual (RN-M5).

Se prueba con un cliente simulado, sin red (RN-U4). Lo que importa: este sistema guarda, lee, lista y borra
solo dentro de su propio prefijo, así que ninguna operación alcanza los objetos de otro sistema.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.api.deps import get_storage
from app.core.config import get_settings
from app.services.storage import StorageLocal, StorageR2
from scripts.purgar_storage import purgar, vencidos

AHORA = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class ErrorS3(Exception):
    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.response = {"Error": {"Code": codigo}}


class CuerpoFalso:
    def __init__(self, datos: bytes):
        self._datos = datos

    def read(self) -> bytes:
        return self._datos


class ClienteFalso:
    """Un bucket S3 en memoria, con paginación de a dos para ejercitar el listado completo."""

    def __init__(self):
        self.objetos: dict[str, dict] = {}
        self.caido = False

    def sembrar(self, clave: str, datos: bytes = b"x", modificado: datetime = AHORA):
        self.objetos[clave] = {"Body": datos, "ContentType": "application/octet-stream", "LastModified": modificado}

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objetos[Key] = {"Body": Body, "ContentType": ContentType, "LastModified": AHORA}

    def get_object(self, *, Bucket, Key):
        if self.caido:
            raise ErrorS3("InternalError")
        if Key not in self.objetos:
            raise ErrorS3("NoSuchKey")
        return {"Body": CuerpoFalso(self.objetos[Key]["Body"])}

    def delete_object(self, *, Bucket, Key):
        self.objetos.pop(Key, None)

    def list_objects_v2(self, *, Bucket, Prefix, ContinuationToken=None):
        claves = sorted(k for k in self.objetos if k.startswith(Prefix))
        inicio = int(ContinuationToken or 0)
        pagina = claves[inicio:inicio + 2]
        hay_mas = inicio + 2 < len(claves)
        return {"Contents": [{"Key": k, "LastModified": self.objetos[k]["LastModified"], "Size": len(self.objetos[k]["Body"])} for k in pagina],
                "IsTruncated": hay_mas, **({"NextContinuationToken": str(inicio + 2)} if hay_mas else {})}


def storage(cliente=None, prefijo="mediflow-triaje") -> StorageR2:
    return StorageR2(endpoint_url="", access_key_id="", secret_access_key="", bucket="mediflow-g10", prefijo=prefijo,
                     cliente=cliente or ClienteFalso())


def bucket_compartido() -> ClienteFalso:
    """Lo de este sistema junto a lo de otro del equipo y a una carpeta vecina de nombre parecido."""
    cliente = ClienteFalso()
    cliente.sembrar("CO/originals/ajeno.pdf", b"ajeno", AHORA - timedelta(days=400))
    cliente.sembrar("mediflow-triaje-otro/co/recibidos/vecino.pdf", b"vecino", AHORA - timedelta(days=400))
    cliente.sembrar("mediflow-triaje/co/recibidos/VIEJO.pdf", b"12345", AHORA - timedelta(days=40))
    cliente.sembrar("mediflow-triaje/co/recibidos/NUEVO.pdf", b"123", AHORA - timedelta(days=2))
    cliente.sembrar("mediflow-triaje/co/rechazados/MALO.pdf", b"1", AHORA - timedelta(days=90))
    return cliente


# --- Guardar y leer --------------------------------------------------------------------------


def test_guarda_y_lee_bajo_el_prefijo_propio_con_su_tipo_de_contenido():
    cliente = ClienteFalso()
    s = storage(cliente)
    s.guardar("co/recibidos/DOC-1.pdf", b"%PDF", "application/pdf")
    assert set(cliente.objetos) == {"mediflow-triaje/co/recibidos/DOC-1.pdf"}
    assert cliente.objetos["mediflow-triaje/co/recibidos/DOC-1.pdf"]["ContentType"] == "application/pdf"
    assert s.leer("co/recibidos/DOC-1.pdf") == b"%PDF"


def test_un_objeto_que_no_existe_es_FileNotFoundError_y_una_caida_es_OSError():
    cliente = ClienteFalso()
    s = storage(cliente)
    with pytest.raises(FileNotFoundError):
        s.leer("co/recibidos/NO-EXISTE.pdf")
    cliente.caido = True
    with pytest.raises(OSError) as error:
        s.leer("co/recibidos/DOC-1.pdf")
    assert not isinstance(error.value, FileNotFoundError)


# --- Listar y borrar: solo lo propio ---------------------------------------------------------


def test_lista_solo_lo_de_este_sistema_y_recorre_todas_las_paginas():
    s = storage(bucket_compartido())
    assert [o.ruta for o in s.listar()] == ["co/rechazados/MALO.pdf", "co/recibidos/NUEVO.pdf", "co/recibidos/VIEJO.pdf"]
    recibidos = s.listar("co/recibidos")
    assert [(o.ruta, o.tamano) for o in recibidos] == [("co/recibidos/NUEVO.pdf", 3), ("co/recibidos/VIEJO.pdf", 5)]
    assert recibidos[1].modificado == AHORA - timedelta(days=40)
    assert s.listar("co/no-existe") == []


def test_borra_solo_el_objeto_pedido_y_borrar_dos_veces_no_falla():
    cliente = bucket_compartido()
    s = storage(cliente)
    s.borrar("co/recibidos/VIEJO.pdf")
    s.borrar("co/recibidos/VIEJO.pdf")
    assert "mediflow-triaje/co/recibidos/VIEJO.pdf" not in cliente.objetos
    assert {"CO/originals/ajeno.pdf", "mediflow-triaje-otro/co/recibidos/vecino.pdf", "mediflow-triaje/co/recibidos/NUEVO.pdf"} <= set(cliente.objetos)


@pytest.mark.parametrize("ruta", ["../CO/originals/ajeno.pdf", "co/../../CO/originals/ajeno.pdf", "/CO/originals/ajeno.pdf"])
def test_ninguna_operacion_sale_del_prefijo_propio(ruta):
    cliente = bucket_compartido()
    antes = dict(cliente.objetos)
    s = storage(cliente)
    for operacion in (lambda: s.guardar(ruta, b"x"), lambda: s.leer(ruta), lambda: s.borrar(ruta), lambda: s.listar(ruta)):
        with pytest.raises(ValueError):
            operacion()
    assert cliente.objetos == antes


def test_una_ruta_vacia_no_guarda_ni_borra():
    cliente = bucket_compartido()
    antes = dict(cliente.objetos)
    for operacion in (lambda: storage(cliente).guardar("", b"x"), lambda: storage(cliente).borrar("")):
        with pytest.raises(ValueError):
            operacion()
    assert cliente.objetos == antes


def test_el_prefijo_es_obligatorio_porque_el_bucket_es_compartido():
    for vacio in ("", "  ", "/"):
        with pytest.raises(ValueError, match="R2_PREFIJO"):
            storage(prefijo=vacio)
    assert storage(prefijo="/mediflow-triaje/").prefijo == "mediflow-triaje"


# --- Purga manual (RN-M5) --------------------------------------------------------------------


def test_la_purga_sin_confirmar_solo_informa_y_con_confirmar_borra_lo_vencido():
    cliente = bucket_compartido()
    s = storage(cliente)
    antes = dict(cliente.objetos)

    simulacro = purgar(s, dias=30, ahora=AHORA)
    assert [o.ruta for o in simulacro] == ["co/rechazados/MALO.pdf", "co/recibidos/VIEJO.pdf"]  # del más antiguo al más reciente
    assert cliente.objetos == antes

    borrados = purgar(s, dias=30, confirmar=True, ahora=AHORA)
    assert [o.ruta for o in borrados] == ["co/rechazados/MALO.pdf", "co/recibidos/VIEJO.pdf"]
    assert set(cliente.objetos) == {"CO/originals/ajeno.pdf", "mediflow-triaje-otro/co/recibidos/vecino.pdf", "mediflow-triaje/co/recibidos/NUEVO.pdf"}


def test_la_purga_se_puede_limitar_a_una_carpeta_y_no_acepta_dias_negativos():
    cliente = bucket_compartido()
    s = storage(cliente)
    assert [o.ruta for o in vencidos(s, dias=30, prefijo="co/recibidos", ahora=AHORA)] == ["co/recibidos/VIEJO.pdf"]
    assert [o.ruta for o in vencidos(s, dias=0, prefijo="co/recibidos", ahora=AHORA)] == ["co/recibidos/VIEJO.pdf", "co/recibidos/NUEVO.pdf"]
    with pytest.raises(ValueError):
        vencidos(s, dias=-1, ahora=AHORA)


def test_la_carpeta_local_tambien_lista_y_borra(tmp_path):
    s = StorageLocal(tmp_path / "bucket")
    s.guardar("co/recibidos/DOC-1.txt", b"hola")
    s.guardar("co/rechazados/DOC-2.txt", b"chao!")
    assert [(o.ruta, o.tamano) for o in s.listar()] == [("co/rechazados/DOC-2.txt", 5), ("co/recibidos/DOC-1.txt", 4)]
    assert [o.ruta for o in s.listar("co/recibidos")] == ["co/recibidos/DOC-1.txt"]
    assert s.listar("no-existe") == []
    # En Windows la fecha del archivo puede quedar un tic por delante del reloj: el límite se fija un segundo después de guardar.
    borrados = purgar(s, dias=0, prefijo="co/recibidos", confirmar=True, ahora=datetime.now(timezone.utc) + timedelta(seconds=1))
    assert [o.ruta for o in borrados] == ["co/recibidos/DOC-1.txt"]
    assert [o.ruta for o in s.listar()] == ["co/rechazados/DOC-2.txt"]
    s.borrar("co/recibidos/DOC-1.txt")  # ya no existe: no falla
    with pytest.raises(ValueError):
        s.borrar("../fuera.txt")


# --- Configuración ---------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint, clave, secreto", [
    ("http://cuenta.r2.cloudflarestorage.com", "k", "s"),   # sin https
    ("https://otro-sitio.example.com", "k", "s"),            # no es R2
    ("https://cuenta.r2.cloudflarestorage.com", "", "s"),    # sin clave
    ("https://cuenta.r2.cloudflarestorage.com", "k", ""),    # sin secreto
])
def test_una_configuracion_incompleta_falla_con_un_mensaje_claro(endpoint, clave, secreto):
    with pytest.raises(ValueError, match="R2 mal configurado"):
        StorageR2(endpoint_url=endpoint, access_key_id=clave, secret_access_key=secreto, bucket="b", prefijo="p")


def test_STORAGE_BACKEND_r2_selecciona_el_bucket_del_equipo_y_vacio_deja_la_regla_de_siempre(monkeypatch, tmp_path):
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "")
    monkeypatch.setattr(settings, "oci_namespace", "")
    monkeypatch.setattr(settings, "storage_local_dir", str(tmp_path))
    get_storage.cache_clear()
    assert isinstance(get_storage(), StorageLocal)

    monkeypatch.setattr(settings, "storage_backend", "r2")
    monkeypatch.setattr(settings, "r2_endpoint_url", "https://cuenta.r2.cloudflarestorage.com/")
    monkeypatch.setattr(settings, "r2_access_key_id", "clave-de-prueba")
    monkeypatch.setattr(settings, "r2_secret_access_key", "secreto-de-prueba")
    monkeypatch.setattr(settings, "r2_bucket_name", "mediflow-g10")
    monkeypatch.setattr(settings, "r2_prefijo", "mediflow-triaje")
    get_storage.cache_clear()
    elegido = get_storage()  # construir el cliente no abre ninguna conexión
    assert isinstance(elegido, StorageR2) and elegido.bucket == "mediflow-g10" and elegido.prefijo == "mediflow-triaje"
    get_storage.cache_clear()
