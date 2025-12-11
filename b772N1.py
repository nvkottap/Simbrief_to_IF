"""
777-200ER Takeoff N1 tables for Infinite Flight

Data: Non-derated takeoff %N1 for packs ON, engine anti-ice ON or OFF,
wing anti-ice OFF or AUTO (full rated takeoff).

Derates (Boeing-style):
  - TO1 / D-TO1: 10% thrust reduction
  - TO2 / D-TO2: 20% thrust reduction

We approximate this by scaling the *excess* N1 above idle (20%):
    N1_derated = 20 + (N1_max - 20) * factor

Infinite Flight slider mapping for 777-200ER:
  slider = 0%   => N1 ≈ 20%
  slider = 100% => N1 ≈ 107%
"""

from typing import Dict, List, Tuple
import bisect
import math

# ---------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------

# Temperatures in °C (rows) taken from your sheet
TEMP_ROWS_C_772: List[int] = [
    -50, -40, -30, -20, -10,
    0, 5, 10, 15, 20,
    25, 30, 35, 40, 45, 50, 60
]

# Altitudes in feet (columns) taken from your sheet
ALT_COLS_FT_772: List[int] = [
    -2000, 0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000
]

# ---------------------------------------------------------------------
# MAX takeoff N1 table (packs ON, eng A/ICE ON/OFF, wing A/I OFF/AUTO)
# Keys: temperature (°C)
# Values: list of N1% at ALT_COLS_FT_772
# NaNs are used where the table is blank (combinations not provided).
# ---------------------------------------------------------------------

N1_ROWS_777_MAX: Dict[int, List[float]] = {
    -50: [86.7, 88.9, 89.4, 89.9, 90.4, 90.9, 91.4, 92.0, 92.7, 93.1, 93.3],
    -40: [88.6, 90.9, 91.4, 91.9, 92.4, 92.9, 93.4, 94.0, 94.8, 95.1, 95.4],
    -30: [90.5, 92.8, 93.3, 93.9, 94.3, 94.8, 95.4, 96.0, 96.8, 97.1, 97.4],
    -20: [92.4, 94.7, 95.2, 95.8, 96.3, 96.8, 97.4, 97.9, 98.7, 99.1, 99.4],
    -10: [94.2, 96.5, 97.1, 97.7, 98.2, 99.7, 99.3, 99.9, 100.7, 101.1, 101.4],
     0: [96.0, 98.3, 98.9, 99.5, 100.0, 100.5, 101.1, 101.7, 102.6, 103.0, 103.3],
     5: [96.8, 99.2, 99.8, 100.4, 100.9, 101.4, 102.1, 102.7, 103.5, 103.9, 104.2],
    10: [97.7, 100.1, 100.7, 101.3, 101.8, 102.4, 103.0, 103.6, 104.4, 104.8, 105.1],
    15: [98.6, 101.0, 101.6, 102.2, 102.7, 103.3, 103.9, 104.5, 105.3, 105.6, 105.5],
    20: [99.4, 101.9, 102.5, 103.1, 103.6, 104.1, 104.8, 105.0, 105.5, 105.3, 104.8],
    25: [100.2, 102.7, 103.4, 104.0, 104.2, 104.3, 104.5, 104.6, 104.6, 104.2, 103.7],
    30: [101.1, 103.6, 103.7, 103.6, 103.6, 103.7, 103.7, 103.7, 103.7, 103.3, 103.0],
    35: [101.6, 103.1, 103.1, 103.1, 103.1, 103.2, 103.1, 103.2, 103.1, 102.7, 102.4],
    40: [100.9, 102.6, 102.3, 102.5, 102.4, 102.5, 102.6, 102.5, 102.5, 102.0, 101.3],
    45: [100.1, 101.4, 101.3, 101.3, 101.4, 101.3, 101.3, 101.3, 101.3, float("nan"), float("nan")],
    50: [99.2, 99.9, 99.9, 99.8, 99.8, 99.9, float("nan"), float("nan"), float("nan"), float("nan"), float("nan")],
    60: [96.6, 96.9, 96.9, 96.9, float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), float("nan"), float("nan")],
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
    If x is outside the axis, clamps to the endpoints.
    """
    if x <= axis[0]:
        return 0, 0, axis[0], axis[0]
    if x >= axis[-1]:
        j = len(axis) - 1
        return j, j, axis[j], axis[j]
    i1 = bisect.bisect_right(axis, x)
    i0 = i1 - 1
    return i0, i1, axis[i0], axis[i1]


def _bilinear_777(
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
    r0_idx, r1_idx, T0, T1 = _locate(TEMP_ROWS_C_772, T_c)
    # locate altitude (ft)
    c0_idx, c1_idx, A0, A1 = _locate(ALT_COLS_FT_772, A_ft)

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
# Thrust and derate logic
# ---------------------------------------------------------------------

def n1_772_max(A_ft: float, T_c: float) -> float:
    """
    Full-rated (non-derated) takeoff N1 for the 777-200ER, packs ON.
    """
    return _bilinear_777(N1_ROWS_777_MAX, A_ft, T_c)


def _apply_derate_from_max(n1_max: float, mode: str) -> float:
    """
    Apply Boeing-style derates:
      TO1 / D-TO1 => 10% thrust reduction
      TO2 / D-TO2 => 20% thrust reduction

    Approximated by scaling the *excess* N1 above idle (20%):
        N1_derated = 20 + (N1_max - 20) * factor
    """
    mode_up = (mode or "").upper()
    if mode_up in {"TO1", "D-TO1"}:
        factor = 0.9
    elif mode_up in {"TO2", "D-TO2"}:
        factor = 0.8
    else:  # treat anything else as MAX
        factor = 1.0

    if math.isnan(n1_max):
        return n1_max

    return 20.0 + (n1_max - 20.0) * factor


def n1_772(A_ft: float, T_c: float, mode: str = "MAX") -> float:
    """
    mode: 'MAX', 'TO1' (D-TO1), or 'TO2' (D-TO2).
    """
    base = n1_772_max(A_ft, T_c)
    return _apply_derate_from_max(base, mode)


# ---------------------------------------------------------------------
# Infinite Flight slider mapping (777-200ER specific)
# ---------------------------------------------------------------------

def slider_from_n1_772(n1_percent: float) -> float:
    """
    Infinite Flight throttle mapping for the 777-200ER:
      slider = 0%   => N1 = 20%
      slider = 100% => N1 = 107%

    So:
      N1 = 20 + (slider / 100) * 87
      slider = (N1 - 20) / 87 * 100
    """
    if math.isnan(n1_percent):
        return float("nan")

    # Clamp N1 to the model’s allowable range
    n1_clamped = max(20.0, min(107.0, n1_percent))

    slider = (n1_clamped - 20.0) / 87.0 * 100.0
    return max(0.0, min(100.0, slider))


def n1_and_slider_772(mode: str, A_ft: float, T_c: float):
    """
    Convenience wrapper: returns (N1%, IF_slider%) for the 777-200ER.
    """
    n1 = n1_772(A_ft, T_c, mode=mode)
    slider = slider_from_n1_772(n1)
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
    Standard entry point for the B777-200ER used by utils.n1_dispatcher.

    - Uses the 777-200ER MAX N1 table plus Boeing-style TO1/TO2 derates.
    - FLEX (if present) is interpreted as MAX at SEL TEMP.
    - `packs_on` is accepted for interface compatibility but currently
      does not change the N1 (no PACKS delta tables yet).
    """

    # Normalize packs flag into 'on' / 'off' for future use
    if isinstance(packs_on, bool):
        packs_flag = "on" if packs_on else "off"
    else:
        p = str(packs_on).strip().lower()
        packs_flag = "off" if p in {"off", "0", "false", "no"} else "on"

    # Normalize mode
    mode = (mode or "MAX").upper()

    # FLEX handling: if FLEX and SEL TEMP is given, use SEL TEMP as the
    # temperature but treat the mode as MAX for table lookup
    temp_for_calc = oat_C
    mode_for_tables = mode
    if mode == "FLEX" and sel_temp_C is not None:
        temp_for_calc = sel_temp_C
        mode_for_tables = "MAX"

    # Delegate to the core 777 logic
    n1_percent, slider_percent = n1_and_slider_772(
        mode_for_tables,
        pressure_alt_ft,
        temp_for_calc,
    )

    # packs_flag and eng_anti_ice_on are currently ignored, but we keep
    # them in the signature for compatibility and future expansion.
    _ = packs_flag
    _ = eng_anti_ice_on

    return n1_percent, slider_percent