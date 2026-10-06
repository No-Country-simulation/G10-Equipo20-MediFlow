class ArchivoInvalido(Exception):
    """Un archivo que no se acepta, con el código explícito que viaja al cliente (RN-A1, RN-O5)."""

    def __init__(self, codigo: str):
        super().__init__(codigo)
        self.codigo = codigo
