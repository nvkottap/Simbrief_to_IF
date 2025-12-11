"""
A380-800 (GP7270) takeoff N1 logic for Infinite Flight.

Assumptions:
- We only model MAX TAKEOFF (MTO). Derates and FLEX are ignored.
- Whatever SimBrief says (FLEX / derate), we use MTO at actual OAT.
- Bleed / anti-ice corrections are not modeled yet (effectively packs ON, anti-ice OFF).

Slider mapping (per user):
    slider = 0%   -> 17% N1
    slider = 100% -> 111% N1
"""

from typing import Dict, List, Tuple
import bisect
import math

# ---------------------------------------------------------------------
# Axes (taken directly from GP7270_takeoff_thr.xlsx)
# ---------------------------------------------------------------------

ALT_COLS_FT_A380: List[int] = [-2000, 0, 2000, 4000, 6000, 8000, 10000, 12000, 14000]

TEMP_ROWS_C_A380: List[int] = [
    -60, -10, -5, 0, 5, 10, 15, 20,
    25, 30, 35, 40, 45, 50, 55, 60
]

# ---------------------------------------------------------------------
# MAX TAKEOFF (MTO) N1 table
# temp_C -> [N1 at each ALT_COLS_FT_A380]
# Values copied from GP7270_takeoff_thr.xlsx
# ---------------------------------------------------------------------

N1_A380_MTO: Dict[int, List[float]] = {
    -60: [97.8, 97.6, 97.4, 97.2, 97.0, 96.7, 97.7, 98.1, 98.1],
    -10: [97.8, 97.6, 97.4, 97.2, 97.0, 96.7, 97.7, 98.1, 98.1],
    -5:  [97.8, 97.6, 97.4, 97.2, 97.0, 96.7, 97.7, 98.1, 98.1],
     0:  [97.8, 97.6, 97.4, 97.2, 97.0, 96.7, 97.7, 98.1, 97.4],
     5:  [97.8, 97.6, 97.4, 97.2, 97.0, 96.7, 97.7, 96.8, 96.9],
    10:  [97.8, 97.6, 97.4, 97.2, 97.0, 96.7, 96.6, 96.6, 97.0],
    15:  [97.8, 97.6, 97.4, 97.2, 97.0, 96.6, 96.2, 95.9, 95.4],
    20:  [97.8, 97.6, 97.4, 97.2, 97.0, 96.4, 96.2, 95.9, 95.4],
    25:  [97.8, 97.6, 97.4, 97.2, 97.0, 96.3, 96.0, 95.8, 95.2],
    30:  [97.8, 97.6, 97.3, 97.1, 96.9, 96.2, 96.0, 95.7, float("nan")],
    35:  [97.8, 97.6, 97.4, 97.1, 96.9, 96.2, float("nan"), float("nan"), float("nan")],
    40:  [97.7, 97.5, 97.3, 97.0, 96.8, float("nan"), float("nan"), float("nan"), float("nan")],
    45:  [97.8, 97.4, 97.2, 97.0, float("nan"), float("nan"), float("nan"), float("nan"), float("nan")],
    50:  [97.7, 97.6, 97.3, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), float("nan")],
    55:  [97.7, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"),
           float("nan"), float("nan"), float("nan")],
    60:  [float("nan")] * 9,
}

# ---------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------

def _interp1(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + (y1 - y0) * t


def _locate(axis: List[float], x: float) -> Tuple[int, int, float, float]:
    """
    Locate bracketing indices and values in a sorted 1D axis.
    Returns (i0, i1, x0, x1) where axis[i0] <= x <= axis[i1].
    Clamps to endpoints if x is outside the axis.
    """
    if x <= axis[0]:
        return 0, 0, axis[0], axis[0]
    if x >= axis[-1]:
        j = len(axis) - 1
        return j, j, axis[j], axis[j]
    i1 = bisect.bisect_right(axis, x)
    i0 = i1 - 1
    return i0, i1, axis[i0], axis[i1]


def _bilinear(
    rows: Dict[int, List[float]],
    A_ft: float,
    T_c: float,
) -> float:
    """
    Bilinear interpolation in (pressure altitude [ft], OAT [°C]).
    """
    # locate temps
    r0_idx, r1_idx, T0, T1 = _locate(TEMP_ROWS_C_A380, T_c)
    # locate altitudes
    c0_idx, c1_idx, A0, A1 = _locate(ALT_COLS_FT_A380, A_ft)

    Q11 = rows[T0][c0_idx]
    Q21 = rows[T0][c1_idx]
    Q12 = rows[T1][c0_idx]
    Q22 = rows[T1][c1_idx]

    # all NaN => undefined
    if all(math.isnan(q) for q in (Q11, Q21, Q12, Q22)):
        return float("nan")

    # degenerate cases
    if T1 == T0 and A1 == A0:
        return Q11
    if T1 == T0:
        return _interp1(A_ft, A0, A1, Q11, Q21)
    if A1 == A0:
        return _interp1(T_c, T0, T1, Q11, Q12)

    # general bilinear interpolation
    fA_T0 = _interp1(A_ft, A0, A1, Q11, Q21)
    fA_T1 = _interp1(A_ft, A0, A1, Q12, Q22)
    return _interp1(T_c, T0, T1, fA_T0, fA_T1)


# ---------------------------------------------------------------------
# Core N1 + slider logic (MTO only)
# ---------------------------------------------------------------------

def n1_a380_mto(A_ft: float, T_c: float) -> float:
    """
    MAX takeoff N1 (MTO) for A380-800, packs ON, anti-ice OFF.
    """
    return _bilinear(N1_A380_MTO, A_ft, T_c)


def slider_from_n1_a380(n1_percent: float) -> float:
    """
    A380-800 IF throttle mapping:
      slider = 0%   => N1 = 17%
      slider = 100% => N1 = 111%
    """
    if math.isnan(n1_percent):
        return float("nan")

    n1_clamped = max(17.0, min(111.0, n1_percent))
    slider = (n1_clamped - 17.0) / 94.0 * 100.0
    return max(0.0, min(100.0, slider))


def n1_and_slider_a380(
    mode: str,
    A_ft: float,
    T_c: float,
    packs: str = "on",
    eng_anti_ice: bool = False,
):
    """
    Main entry point for the app: returns (N1%, IF_slider%) for A380-800.

    Currently we IGNORE `mode`, `packs`, and `eng_anti_ice` and always use
    the MAX takeoff (MTO) table at the given altitude and temperature,
    as per your design.
    """
    n1 = n1_a380_mto(A_ft, T_c)
    slider = slider_from_n1_a380(n1)
    return n1, slider


def compute_takeoff_n1(
    pressure_alt_ft: float,
    oat_C: float,
    mode: str,
    packs_on,
    eng_anti_ice_on: bool,
    sel_temp_C: float | None = None,
):
    """
    Standard dispatcher entry point for the A380-800.
    Per design, always uses MAX mode.
    """

    core_function = n1_and_slider_a380

    # Packs → string
    if isinstance(packs_on, bool):
        packs_flag = "on" if packs_on else "off"
    else:
        packs_flag = "off" if str(packs_on).strip().lower() in {"off", "false", "0"} else "on"

    # A380 ALWAYS uses MAX tables
    mode_for_tables = "MAX"
    temp_for_calc = oat_C

    n1, slider = core_function(
        mode_for_tables,
        pressure_alt_ft,
        temp_for_calc,
        packs=packs_flag,
        eng_anti_ice=eng_anti_ice_on,
    )

    return n1, slider