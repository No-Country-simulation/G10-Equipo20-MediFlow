"""Escala a mano las alertas críticas sin acuse vencidas (RN-F2). La API lo hace sola cada ESCALAMIENTO_CADA_S segundos.

Uso: python -m scripts.escalar_alertas
"""
from app.services.escalamiento import escalar_una_vuelta


def main() -> int:
    escaladas = escalar_una_vuelta()
    print(f"{len(escaladas)} alertas escaladas" + (": " + ", ".join(escaladas) if escaladas else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
