"""
A220-300 (A223) Takeoff N1 tables for Infinite Flight.

Data source:
  - maxto.xlsx : MAX takeoff N1
  - to1.xlsx   : TO1 derate N1
  - to2.xlsx   : TO2 derate N1

All three tables share the same axes:

  °C rows:  -54, -50, -45, -40, -35, -30, -25, -20,
            -15, -10,  -5,   0,   5,  10,  15,  20,
             25,  30,  35,  40,  45,  53

  Pressure altitude (ft) columns:
            -2000, 0, 1000, 2000, 3000, 4000,
             6000, 8000, 10000, 12000, 14500

Infinite Flight slider mapping for A220-300 (assumed, see note):
  - slider = 0%   => N1 = 20%
  - slider = 100% => N1 = 101%

If you confirm a different mapping for the A220, just adjust
`slider_from_n1_a223` accordingly.
"""

from typing import Dict, List, Tuple
import bisect
import math

# ---------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------

TEMP_ROWS_C_A223: List[int] = [
    -54, -50, -45, -40, -35, -30, -25, -20,
    -15, -10, -5, 0, 5, 10, 15, 20,
    25, 30, 35, 40, 45, 53,
]

ALT_COLS_FT_A223: List[int] = [
    -2000, 0, 1000, 2000, 3000, 4000,
    6000, 8000, 10000, 12000, 14500,
]

# Column order is:
# ['-2000','0','1000','2000','3000','4000','6000','8000','10000','12000','14500']


# ---------------------------------------------------------------------
# MAX takeoff N1 table (maxto.xlsx)
# Keys: °C
# Values: [N1 @ -2000, 0, 1000, ..., 14500 ft]
# NaN = table not defined there.
# ---------------------------------------------------------------------

N1_ROWS_A223_MAX: Dict[int, List[float]] = {
    -54: [73.6, 75.9, 76.5, 77.2, 77.8, 78.4, 79.5, 80.6, 81.6, 82.6, 83.7],
    -50: [74.2, 76.6, 77.2, 77.9, 78.5, 79.1, 80.3, 81.3, 82.4, 83.3, 84.4],
    -45: [75.1, 77.4, 78.1, 78.7, 79.3, 79.9, 81.1, 82.2, 83.3, 84.3, 85.4],
    -40: [75.9, 78.2, 78.9, 79.6, 80.2, 80.8, 82.0, 83.1, 84.2, 85.2, 86.3],
    -35: [76.7, 79.1, 79.7, 80.4, 81.0, 81.7, 82.9, 84.0, 85.1, 86.1, 87.2],
    -30: [77.4, 79.9, 80.6, 81.2, 81.9, 82.5, 83.7, 84.9, 85.9, 86.9, 88.1],
    -25: [78.2, 80.7, 81.4, 82.1, 82.7, 83.3, 84.6, 85.7, 86.8, 87.8, 89.0],
    -20: [79.0, 81.5, 82.2, 82.9, 83.5, 84.2, 85.4, 86.6, 87.7, 88.7, 89.8],
    -15: [79.8, 82.3, 83.0, 83.7, 84.3, 85.0, 86.2, 87.4, 88.5, 89.5, 90.7],
    -10: [80.5, 83.1, 83.8, 84.5, 85.1, 85.7, 87.0, 88.2, 89.1, 90.2, 91.6],
    -5: [81.3, 83.8, 84.6, 85.3, 85.9, 86.8, 87.9, 89.1, 90.2, 91.2, 92.4],
    0: [82.0, 84.6, 85.3, 86.1, 86.7, 87.4, 88.7, 89.9, 91.0, 92.1, 93.3],
    5: [82.8, 85.4, 86.1, 87.0, 87.5, 88.2, 89.5, 90.7, 91.8, 92.9, 93.3],
    10: [83.5, 86.2, 86.9, 87.6, 88.3, 89.0, 90.3, 91.5, 92.6, 92.8, 92.7],
    15: [84.3, 86.9, 87.7, 88.4, 89.1, 89.8, 91.1, 92.3, 92.0, 91.9, 92.0],
    20: [85.0, 87.7, 88.4, 89.2, 89.9, 90.5, 91.5, 91.2, 91.0, 90.9, 91.0],
    25: [85.7, 88.4, 89.2, 89.9, 90.3, 90.3, 90.2, 90.1, 89.7, 89.7, 89.8],
    30: [86.5, 89.2, 89.2, 89.2, 89.2, 89.2, 89.1, 88.9, 88.5, 88.5, 88.7],
    35: [86.8, 88.0, 88.0, 88.0, 88.0, 87.9, 87.8, 87.6, 87.4, 87.4, 87.5],
    40: [85.6, 86.8, 86.8, 86.8, 87.6, 86.7, 86.6, 86.4, 86.4, 86.6, 86.1],
    45: [84.2, 85.5, 85.5, 85.5, 85.5, 85.4, 85.4, 85.4, 85.4, 85.4, float("nan")],
    53: [82.3, 83.6, 83.6, 83.4, 83.4, 83.4, 83.3, 83.2, float("nan"), float("nan"), float("nan")],
}

# ---------------------------------------------------------------------
# TO1 derated table (to1.xlsx)
# ---------------------------------------------------------------------

N1_ROWS_A223_TO1: Dict[int, List[float]] = {
    -54: [70.8, 73.1, 73.7, 74.3, 74.9, 75.6, 76.6, 77.6, 78.5, 79.5, 80.5],
    -50: [71.4, 73.7, 74.3, 75.0, 75.6, 76.2, 77.3, 78.3, 79.2, 80.2, 81.2],
    -45: [72.3, 74.5, 75.2, 75.9, 76.5, 77.1, 78.2, 79.2, 80.1, 81.1, 82.1],
    -40: [73.6, 76.1, 76.8, 77.3, 77.8, 78.4, 79.6, 80.6, 81.2, 82.0, 83.0],
    -35: [73.6, 76.1, 76.7, 77.4, 78.0, 78.6, 79.8, 80.8, 81.2, 82.0, 83.0],
    -30: [74.3, 76.9, 77.6, 78.2, 78.9, 79.5, 80.7, 81.8, 82.2, 83.1, 84.0],
    -25: [75.3, 77.9, 78.4, 79.0, 79.8, 80.4, 81.6, 82.7, 83.1, 84.0, 84.9],
    -20: [76.6, 78.7, 79.4, 80.0, 81.1, 81.7, 82.9, 84.0, 84.2, 85.1, 86.0],
    -15: [76.9, 79.8, 80.6, 81.2, 81.8, 82.4, 83.7, 84.8, 85.2, 86.0, 86.9],
    -10: [77.5, 80.7, 81.4, 82.1, 82.8, 83.4, 84.6, 85.8, 86.1, 86.9, 87.8],
    -5: [78.2, 81.7, 82.1, 82.8, 83.6, 84.4, 85.5, 86.8, 87.1, 87.9, 88.8],
    0: [79.0, 82.7, 83.0, 83.8, 84.5, 85.3, 86.6, 87.8, 88.0, 88.9, 89.8],
    5: [79.7, 82.9, 83.2, 83.9, 84.6, 85.2, 86.4, 87.7, 88.0, 88.8, 89.7],
    10: [80.4, 83.6, 84.3, 85.0, 85.6, 86.3, 87.5, 88.8, 89.0, 89.9, 90.8],
    15: [81.1, 84.7, 85.2, 85.9, 86.5, 87.2, 88.3, 89.6, 89.8, 90.7, 91.6],
    20: [81.7, 85.4, 86.0, 86.7, 87.4, 88.0, 89.2, 90.4, 90.6, 91.4, 92.2],
    25: [82.5, 85.9, 86.5, 86.6, 87.3, 87.8, 88.7, 89.3, 89.7, 89.8, 90.2],
    30: [83.4, 85.8, 86.2, 86.0, 86.8, 87.4, 87.9, 88.9, 88.5, 88.7, 88.7],
    35: [84.3, 83.3, 83.2, 83.2, 83.2, 83.2, 83.2, 83.2, 87.1, 87.1, 87.2],
    40: [83.3, 82.2, 82.3, 82.2, 82.2, 82.1, 82.1, 82.0, 86.4, 86.6, 86.5],
    45: [81.1, 81.3, 82.3, 82.2, 82.2, 81.8, 81.7, 81.4, 85.4, 85.6, float("nan")],
    53: [79.2, 80.5, 80.4, 80.3, 80.2, 80.1, 80.0, 79.6, float("nan"), float("nan"), float("nan")],
}

# ---------------------------------------------------------------------
# TO2 derated table (to2.xlsx)
# ---------------------------------------------------------------------

N1_ROWS_A223_TO2: Dict[int, List[float]] = {
    -54: [68.1, 70.3, 71.5, 72.1, 72.7, 73.7, 74.7, 75.6, 76.6, 77.6, 78.5],
    -50: [68.7, 70.9, 71.6, 72.2, 72.7, 73.7, 74.5, 76.3, 77.3, 78.2, 79.5],
    -45: [69.9, 72.1, 73.0, 73.4, 74.2, 74.9, 75.7, 76.3, 77.0, 78.1, 79.4],
    -40: [70.9, 73.2, 74.3, 74.9, 75.6, 76.7, 76.6, 77.8, 78.9, 79.7, 80.7],
    -35: [71.9, 73.2, 74.5, 75.1, 75.7, 76.6, 76.6, 77.8, 78.9, 79.8, 80.7],
    -30: [72.5, 73.8, 75.2, 75.9, 76.6, 77.6, 77.6, 78.7, 79.8, 80.7, 81.6],
    -25: [72.4, 74.8, 75.6, 76.7, 77.4, 78.4, 78.4, 79.4, 80.4, 81.4, 82.4],
    -20: [71.7, 75.2, 75.4, 76.9, 77.8, 79.0, 78.9, 79.7, 80.2, 81.3, 82.4],
    -15: [71.0, 76.2, 76.7, 77.6, 78.8, 80.1, 80.1, 81.2, 82.2, 82.9, 84.0],
    -10: [72.0, 77.6, 78.1, 79.0, 79.7, 81.2, 81.4, 82.5, 83.6, 84.2, 85.4],
    -5: [73.0, 77.7, 79.0, 80.0, 80.9, 82.0, 82.6, 83.7, 84.8, 85.6, 86.2],
    0: [75.2, 78.4, 79.7, 80.7, 81.4, 82.8, 83.6, 84.8, 85.8, 86.6, 87.2],
    5: [77.8, 77.9, 79.1, 80.1, 80.8, 82.1, 83.0, 84.0, 85.2, 85.4, 87.0],
    10: [79.8, 79.1, 80.2, 81.2, 81.7, 82.8, 83.6, 85.0, 86.2, 87.6, 86.7],
    15: [82.1, 79.8, 80.4, 81.8, 82.3, 83.3, 84.0, 84.6, 86.4, 86.6, 86.4],
    20: [84.7, 81.0, 81.4, 82.7, 83.2, 84.2, 85.4, 85.5, 85.4, 86.6, 86.6],
    25: [87.2, 81.7, 82.7, 83.4, 83.7, 84.0, 84.5, 85.4, 85.4, 86.6, 86.0],
    30: [89.2, 81.8, 82.7, 82.9, 82.7, 82.9, 83.3, 83.8, 85.0, 86.0, 86.0],
    35: [90.8, 78.4, 78.8, 79.0, 79.3, 79.9, 80.6, 81.2, 82.0, 82.8, 83.0],
    40: [92.0, 78.0, 78.4, 78.7, 78.8, 79.3, 79.7, 79.9, 80.9, 81.2, 81.6],
    45: [77.0, 77.3, 77.7, 77.0, 77.6, 78.1, 78.7, 79.6, 78.1, 78.4, float("nan")],
    53: [75.7, 77.3, 77.1, 77.0, 76.9, 76.8, 76.8, 76.6, float("nan"), float("nan"), float("nan")],
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
    Bilinear interpolation in (pressure altitude [ft], OAT [°C]) space.

    NOTE: Some high-T/high-alt cells are NaN (not defined in the table).
    If the interpolation region includes NaNs, the result may be NaN; the
    caller should treat that as "outside certified table".
    """
    # locate temps
    r0_idx, r1_idx, T0, T1 = _locate(TEMP_ROWS_C_A223, T_c)
    # locate altitude (ft)
    c0_idx, c1_idx, A0, A1 = _locate(ALT_COLS_FT_A223, A_ft)

    Q11 = rows[T0][c0_idx]
    Q21 = rows[T0][c1_idx]
    Q12 = rows[T1][c0_idx]
    Q22 = rows[T1][c1_idx]

    # If all four are NaN, just return NaN
    if all(math.isnan(q) for q in (Q11, Q21, Q12, Q22)):
        return float("nan")

    # Single-point cases
    if T1 == T0 and A1 == A0:
        return Q11
    if T1 == T0:
        return _interp1(A_ft, A0, A1, Q11, Q21)
    if A1 == A0:
        return _interp1(T_c, T0, T1, Q11, Q12)

    # General bilinear interpolation
    fA_T0 = _interp1(A_ft, A0, A1, Q11, Q21)
    fA_T1 = _interp1(A_ft, A0, A1, Q12, Q22)
    return _interp1(T_c, T0, T1, fA_T0, fA_T1)


# ---------------------------------------------------------------------
# Core N1 functions
# ---------------------------------------------------------------------

def n1_a223_max(A_ft: float, T_c: float) -> float:
    """Full-rated MAX takeoff N1 for the A220-300."""
    return _bilinear(N1_ROWS_A223_MAX, A_ft, T_c)


def n1_a223_to1(A_ft: float, T_c: float) -> float:
    """TO1 derated takeoff N1 for the A220-300."""
    return _bilinear(N1_ROWS_A223_TO1, A_ft, T_c)


def n1_a223_to2(A_ft: float, T_c: float) -> float:
    """TO2 derated takeoff N1 for the A220-300."""
    return _bilinear(N1_ROWS_A223_TO2, A_ft, T_c)


def n1_a223(A_ft: float, T_c: float, mode: str = "MAX") -> float:
    """
    mode: 'MAX', 'TO1' (D-TO1), or 'TO2' (D-TO2).
    """
    mode_up = (mode or "").upper()
    if "TO2" in mode_up:
        return n1_a223_to2(A_ft, T_c)
    elif "TO1" in mode_up:
        return n1_a223_to1(A_ft, T_c)
    else:
        return n1_a223_max(A_ft, T_c)


# ---------------------------------------------------------------------
# Infinite Flight slider mapping (A220-300, assumed)
# ---------------------------------------------------------------------

def slider_from_n1_a223(n1_percent: float) -> float:
    """
    Infinite Flight throttle mapping for the A220-300 (assumed):

      slider = 0%   => N1 = 20%
      slider = 100% => N1 = 101%

    So:
      N1 = 20 + (slider / 100) * 81
      slider = (N1 - 20) / 81 * 100
    """
    if math.isnan(n1_percent):
        return float("nan")

    # Clamp N1 into the modeled range
    n1_clamped = max(20.0, min(101.0, n1_percent))
    slider = (n1_clamped - 20.0) / 81.0 * 100.0
    return max(0.0, min(100.0, slider))


def n1_and_slider_a223(
    mode: str,
    A_ft: float,
    T_c: float,
    packs: str = "on",
    eng_anti_ice: bool = False,
):
    """
    Convenience wrapper: returns (N1%, IF_slider%) for the A220-300.

    Currently ignores `packs` and `eng_anti_ice` because we don't have
    separate delta tables for those yet, but the signature matches the
    737 MAX 8's so it can be dropped into the same dispatcher.
    """
    n1 = n1_a223(A_ft, T_c, mode=mode)
    slider = slider_from_n1_a223(n1)
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
    Standard dispatcher entry point for the A220-300.
    Delegates to this module’s n1_and_slider().
    """

    core_function = n1_and_slider_a223

    # Packs → string
    if isinstance(packs_on, bool):
        packs_flag = "on" if packs_on else "off"
    else:
        packs_flag = "off" if str(packs_on).strip().lower() in {"off", "false", "0"} else "on"

    mode = (mode or "MAX").upper()

    temp_for_calc = oat_C
    mode_for_tables = mode
    if mode == "FLEX" and sel_temp_C:
        temp_for_calc = sel_temp_C
        mode_for_tables = "MAX"

    n1, slider = core_function(
        mode_for_tables,
        pressure_alt_ft,
        temp_for_calc,
        packs=packs_flag,
        eng_anti_ice=eng_anti_ice_on,
    )

    return n1, slider