"""Supported intake countries. These codes are also R2 key prefixes."""

COUNTRIES = (
    ("AR", "Argentina"), ("BO", "Bolivia"), ("BR", "Brasil"),
    ("CL", "Chile"), ("CO", "Colombia"), ("EC", "Ecuador"),
    ("PY", "Paraguay"), ("PE", "Perú"), ("UY", "Uruguay"),
    ("VE", "Venezuela"), ("MX", "México"),
)
COUNTRY_CODES = frozenset(code for code, _ in COUNTRIES)
