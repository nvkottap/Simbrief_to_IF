# utils/n1_dispatcher.py

"""
N1 dispatcher for multiple aircraft types.

Takes normalized SimBrief takeoff info (from utils.simbrief_parser) plus an
aircraft key, and returns:
    - N1_percent (float)
    - IF_slider_percent (float)
    - flaps
    - thrust mode info
    - V-speeds
    - and some context fields

Main entry point used by app.py:
    compute_takeoff_from_info(info: dict, aircraft: str) -> dict
"""

from __future__ import annotations

from typing import Dict, Any, Callable

from utils.simbrief_parser import is_flex_active


# ============================================================================
# Import aircraft-specific modules (not individual functions)
# ============================================================================

import b737max8N1          # B737 MAX 8
import b772N1              # B777-200ER
try:
    import b773N1          # B777-300ER (if present)
except ImportError:
    b773N1 = None          # type: ignore
import a223N1              # A220-300
import a388N1              # A380-800


SUPPORTED_AIRCRAFT = {
    "B737 MAX 8",
    "B777-200ER",
    #"B777-300ER",
    "A220-300",
    "A380-800",
}


# ============================================================================
# Helpers to discover a compute function in a module
# ============================================================================

def _find_compute_func(module, aircraft_label: str) -> Callable[..., Any]:
    """
    Try several common function names in the given module, return the first match.

    Expected callable signature:
        fn(
            pressure_alt_ft: float,
            oat_C: float,
            mode: str,               # 'MAX', 'TO1', 'TO2', maybe 'FLEX'
            packs_on: bool,
            eng_anti_ice_on: bool,
            sel_temp_C: float | None = None,
        ) -> (n1_percent: float, if_slider_percent: float)
    """
    candidate_names = [
        "compute_takeoff_n1",
        "compute_takeoff",
        "compute_n1",
        # more specific guesses that might exist in your codebase
        "compute_737max8_takeoff",
        "compute_777200er_takeoff",
        "compute_777300er_takeoff",
        "compute_a223_takeoff",
        "compute_a380_takeoff",
    ]

    for name in candidate_names:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn

    available = [n for n in dir(module) if callable(getattr(module, n))]
    raise ValueError(
        f"No suitable N1 compute function found in module '{module.__name__}' "
        f"for aircraft '{aircraft_label}'.\n"
        f"Please define a function such as 'compute_takeoff_n1' with signature:\n\n"
        f"    def compute_takeoff_n1(pressure_alt_ft, oat_C, mode, packs_on, "
        f"eng_anti_ice_on, sel_temp_C=None) -> (n1_percent, if_slider_percent)\n\n"
        f"Available callables in that module are: {available}"
    )


def _select_n1_function(aircraft: str) -> Callable[..., Any]:
    """
    Map our internal aircraft key to the appropriate compute function.
    """
    if aircraft == "B737 MAX 8":
        return _find_compute_func(b737max8N1, aircraft)

    if aircraft == "B777-200ER":
        return _find_compute_func(b772N1, aircraft)

    if aircraft == "B777-300ER":
        if b773N1 is None:
            raise ValueError(
                "B777-300ER selected but 'b773N1.py' is not present or failed to import. "
                "Add that module or remove B777-300ER from supported aircraft."
            )
        return _find_compute_func(b773N1, aircraft)  # type: ignore[arg-type]

    if aircraft == "A220-300":
        return _find_compute_func(a223N1, aircraft)

    if aircraft == "A380-800":
        return _find_compute_func(a388N1, aircraft)

    raise ValueError(f"No N1 function configured for aircraft '{aircraft}'.")


# ============================================================================
# Public API
# ============================================================================

def compute_takeoff_from_info(info: Dict[str, Any], aircraft: str) -> Dict[str, Any]:
    """
    Main dispatcher: take the normalized SimBrief info dict (from
    parse_takeoff_from_json() or parse_takeoff_from_text()) and an
    aircraft key, and return a result dict with N1, IF slider, flaps, etc.

    Expected keys in `info` (from utils.simbrief_parser):

        airport (str)             e.g. 'KIAH'
        runway (str)              e.g. '15L'
        oat_C (float)             outside air temperature at the airport
        elevation_ft (float)      field elevation (text path)
        pressure_alt_ft (float)   pressure altitude (JSON path; may be absent)
        qnh_inhg (float)          QNH in inHg (JSON path; optional)

        mode_raw (str)            e.g. 'D-TO2', 'FLEX', 'TO'
        mode_normalized (str)     'MAX', 'TO1', 'TO2', 'FLEX'
        bleeds (str)              'ON' / 'OFF' / 'AUTO'
        packs_for_calc (str/bool) 'on'/'off' or True/False
        aice_raw (str)            'OFF' / 'ENG' / 'ALL' / ...
        anti_ice_for_calc (bool)  True if engine anti-ice ON
        sel_temp_C (float|None)   FLEX/assumed temp, if any

        flaps (str)               e.g. '5', '1+F', 'FULL', '25'
        speeds (dict)             {'V1': int|None, 'VR': int|None, 'V2': int|None}
    """
    if aircraft not in SUPPORTED_AIRCRAFT:
        raise ValueError(
            f"compute_takeoff_from_info: aircraft '{aircraft}' is not in SUPPORTED_AIRCRAFT."
        )

    n1_func = _select_n1_function(aircraft)

    # ----------------------------------------------------------------------
    # Core inputs
    # ----------------------------------------------------------------------
    # Prefer pressure altitude if available (JSON path), otherwise
    # fall back to field elevation (text path).
    pressure_alt_ft = info.get("pressure_alt_ft")
    if pressure_alt_ft is None:
        pressure_alt_ft = info.get("elevation_ft", 0.0)

    oat_C = info.get("oat_C")
    mode_raw = info.get("mode_raw")
    mode_norm = info.get("mode_normalized") or "MAX"
    sel_temp_C = info.get("sel_temp_C")

    # --- FIXED: robust handling of packs_for_calc (bool or string) ---
    raw_packs = info.get("packs_for_calc", "on")
    if isinstance(raw_packs, bool):
        packs_flag = "on" if raw_packs else "off"
    else:
        packs_flag = str(raw_packs).strip().lower()

    packs_on = packs_flag != "off"

    anti_ice_on = bool(info.get("anti_ice_for_calc"))

    # FLEX / assumed-temp logic
    flex_active = is_flex_active(oat_C, sel_temp_C, mode_raw)

    # Mode used for table calculations:
    calc_mode = mode_norm
    calc_sel_temp = sel_temp_C if flex_active else None

    # For A380 you decided: always treat as MAX takeoff (ignore derates/FLEX).
    if aircraft == "A380-800":
        calc_mode = "MAX"
        calc_sel_temp = None

    # ----------------------------------------------------------------------
    # Call aircraft-specific N1 function
    # ----------------------------------------------------------------------
    n1_percent, if_slider_percent = n1_func(
        pressure_alt_ft=pressure_alt_ft,
        oat_C=oat_C,
        mode=calc_mode,
        packs_on=packs_on,
        eng_anti_ice_on=anti_ice_on,
        sel_temp_C=calc_sel_temp,
    )

    # ----------------------------------------------------------------------
    # Build result dict for the UI
    # ----------------------------------------------------------------------
    speeds = info.get("speeds") or {}
    result: Dict[str, Any] = {
        "aircraft": aircraft,
        "airport": info.get("airport"),
        "runway": info.get("runway"),

        "N1_percent": n1_percent,
        "IF_slider_percent": if_slider_percent,

        "flaps": info.get("flaps"),
        "thrust_mode_raw": mode_raw or mode_norm,
        "thrust_mode_normalized": mode_norm,
        "speeds": {
            "V1": speeds.get("V1"),
            "VR": speeds.get("VR"),
            "V2": speeds.get("V2"),
        },

        "packs_for_calc": packs_flag,
        "anti_ice_for_calc": anti_ice_on,
        "flex_active": flex_active,

        "oat_C": oat_C,
        "pressure_alt_ft": pressure_alt_ft,
        "sel_temp_C": sel_temp_C,
    }

    return result