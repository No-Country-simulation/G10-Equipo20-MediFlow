"""NEWS2 calculado en código (RN-D3, RN-D4). Los umbrales no son configurables (RN-D5).

Las bandas de puntuación son las del Royal College of Physicians (NEWS2, 2017).
No se puntúa el oxígeno suplementario porque el documento rara vez lo declara de
forma estructurada; se anota como limitación conocida.
"""
from dataclasses import dataclass, field

from app.packs.modelos import Umbrales
from app.schemas.propuesta import SignosVitalesPropuestos

_CONCIENCIA_ALERTA = {"alerta", "alert", "a", "consciente", "orientado", "normal"}


@dataclass
class ResultadoNEWS2:
    aplicable: bool
    hay_signos: bool
    total: int | None
    completo: bool
    puntajes: dict[str, int] = field(default_factory=dict)
    escala_spo2: int = 1
    critico: bool = False
    motivos: list[str] = field(default_factory=list)
    motivo_no_aplicable: str | None = None


def _puntos_fr(fr: int) -> int:
    if fr <= 8 or fr >= 25:
        return 3
    if 21 <= fr <= 24:
        return 2
    if 9 <= fr <= 11:
        return 1
    return 0


def _puntos_spo2_escala1(spo2: int) -> int:
    if spo2 <= 91:
        return 3
    if spo2 <= 93:
        return 2
    if spo2 <= 95:
        return 1
    return 0


def _puntos_spo2_escala2(spo2: int) -> int:
    # RN-D4: objetivo 88-92 % en insuficiencia respiratoria hipercápnica.
    if spo2 <= 83:
        return 3
    if spo2 <= 85:
        return 2
    if spo2 <= 87:
        return 1
    return 0  # 88-92 es el objetivo; por encima, sin dato de oxígeno, se puntúa 0


def _puntos_fc(fc: int) -> int:
    if fc <= 40 or fc >= 131:
        return 3
    if 111 <= fc <= 130:
        return 2
    if 41 <= fc <= 50 or 91 <= fc <= 110:
        return 1
    return 0


def _puntos_pas(pas: int) -> int:
    if pas <= 90 or pas >= 220:
        return 3
    if pas <= 100:
        return 2
    if pas <= 110:
        return 1
    return 0


def _puntos_temp(temp: float) -> int:
    if temp <= 35.0:
        return 3
    if temp >= 39.1:
        return 2
    if temp <= 36.0 or temp >= 38.1:
        return 1
    return 0


def _puntos_conciencia(nivel: str) -> int:
    return 0 if nivel.strip().lower() in _CONCIENCIA_ALERTA else 3


def calcular_news2(
    signos: SignosVitalesPropuestos,
    *,
    edad: int | None,
    umbrales: Umbrales,
    epoc_hipercapnico: bool = False,
    embarazo: bool = False,
) -> ResultadoNEWS2:
    valores = {
        "FR": signos.FR, "SpO2": signos.SpO2, "FC": signos.FC, "PAS": signos.PAS,
        "Temp": signos.Temp, "nivel_conciencia": signos.nivel_conciencia,
    }
    hay_signos = any(v is not None for v in valores.values())

    motivo_no_aplicable = None
    if edad is None:
        motivo_no_aplicable = "sin_edad"  # RN-N4
    elif edad < umbrales.news2.edad_minima:
        motivo_no_aplicable = "menor_de_16"  # RN-N1
    elif embarazo:
        motivo_no_aplicable = "embarazo"  # RN-N2
    aplicable = motivo_no_aplicable is None

    if not hay_signos or not aplicable:
        return ResultadoNEWS2(aplicable, hay_signos, None, False, motivo_no_aplicable=motivo_no_aplicable)

    escala = 2 if epoc_hipercapnico else 1
    puntajes: dict[str, int] = {}
    if signos.FR is not None:
        puntajes["FR"] = _puntos_fr(signos.FR)
    if signos.SpO2 is not None:
        puntajes["SpO2"] = (_puntos_spo2_escala2 if escala == 2 else _puntos_spo2_escala1)(signos.SpO2)
    if signos.FC is not None:
        puntajes["FC"] = _puntos_fc(signos.FC)
    if signos.PAS is not None:
        puntajes["PAS"] = _puntos_pas(signos.PAS)
    if signos.Temp is not None:
        puntajes["Temp"] = _puntos_temp(signos.Temp)
    if signos.nivel_conciencia is not None:
        puntajes["nivel_conciencia"] = _puntos_conciencia(signos.nivel_conciencia)

    n = umbrales.news2
    motivos: list[str] = []
    if signos.FR is not None and (signos.FR <= n.fr_bajo or signos.FR >= n.fr_alto):
        motivos.append("FR")
    if signos.SpO2 is not None and ((escala == 1 and signos.SpO2 <= n.spo2_bajo) or (escala == 2 and signos.SpO2 <= 83)):
        motivos.append("SpO2")
    if signos.FC is not None and (signos.FC <= n.fc_bajo or signos.FC >= n.fc_alto):
        motivos.append("FC")
    if signos.PAS is not None and signos.PAS <= n.pas_bajo:
        motivos.append("PAS")
    if signos.nivel_conciencia is not None and puntajes["nivel_conciencia"] == 3:
        motivos.append("nivel_conciencia")

    total = sum(puntajes.values())
    if total >= n.total_critico:
        motivos.append("NEWS2_total")

    return ResultadoNEWS2(
        aplicable=True,
        hay_signos=True,
        total=total,
        completo=len(puntajes) == 6,
        puntajes=puntajes,
        escala_spo2=escala,
        critico=bool(motivos),
        motivos=motivos,
    )
