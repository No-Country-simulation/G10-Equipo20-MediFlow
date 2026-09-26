"""Errores de negocio que la API traduce a códigos HTTP."""


class ErrorDeRevision(Exception):
    def __init__(self, codigo: int, detalle: str):
        super().__init__(detalle)
        self.codigo = codigo
        self.detalle = detalle
