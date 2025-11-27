# utils/n1_dispatcher.py

from typing import Any, Dict

from utils.simbrief_parser import (
    parse_simbrief_takeoff_block,
    is_flex_active,
)

# N1 logic modules for each aircraft
from b737max8N1 import n1_and_slider as n1_and_slider_737
from b772erN1 import n1_and_slider_772
from a223N1 import n1_and_slider_a223
from a380N1 import n1_and_slider_a380


def compute_n1_and_slider_for_aircraft(
    aircraft: str,
    mode_norm: str,
    elev_ft: int,
    temp_C: int,
    packs: str,
    eng_aice: bool,
):
    """
    Dispatch to the correct N1 + slider function depending on aircraft.
    """
    if aircraft == "B737 MAX 8":
        return n1_and_slider_737(
            mode_norm,
            elev_ft,
            temp_C,
            packs=packs,
            eng_anti_ice=eng_aice,
        )
    elif aircraft == "B777-200ER":
        return n1_and_slider_772(
            mode_norm,
            elev_ft,
            temp_C,
        )
    elif aircraft == "A220-300":
        return n1_and_slider_a223(
            mode_norm,
            elev_ft,
            temp_C,
            packs=packs,
            eng_anti_ice=eng_aice,
        )
    elif aircraft == "A380-800":
        # For A380 we always use MAX MTO at actual OAT; mode_norm is ignored.
        return n1_and_slider_a380(
            mode_norm,
            elev_ft,
            temp_C,
        )
    else:
        raise ValueError(f"Unsupported aircraft for N1 calc: {aircraft}")


def compute_takeoff_from_simbrief(text: str, aircraft: str) -> Dict[str, Any]:
    """
    Returns:
      - operational N1 + slider (base or FLEX, depending on SimBrief & aircraft)
      - flaps, thrust profile name, and V-speeds
    for the given aircraft type.
    """
    info = parse_simbrief_takeoff_block(text)

    oat = info["oat_C"]
    sel_temp = info["sel_temp_C"]
    mode_raw = info["mode_raw"]              # e.g. 'D-TO2', 'FLEX'
    mode_norm = info["mode_normalized"]      # 'MAX' | 'TO1' | 'TO2' | 'FLEX'
    elev_ft = info["elevation_ft"]
    packs = info["packs_for_calc"]           # 'on' | 'off'
    eng_aice = info["anti_ice_for_calc"]     # bool

    # 1) Base N1 at actual OAT
    base_n1, base_slider = compute_n1_and_slider_for_aircraft(
        aircraft,
        mode_norm,
        elev_ft,
        oat,
        packs,
        eng_aice,
    )

    # 2) FLEX logic
    if aircraft == "A380-800":
        # For A380 we ALWAYS use MAX MTO at actual OAT, ignoring FLEX/derates.
        flex_active = False
    else:
        flex_active = is_flex_active(oat, sel_temp, mode_raw)

    if flex_active and sel_temp is not None:
        flex_n1, flex_slider = compute_n1_and_slider_for_aircraft(
            aircraft,
            mode_norm,
            elev_ft,
            sel_temp,
            packs,
            eng_aice,
        )
        op_n1 = flex_n1
        op_slider = flex_slider
        temp_used = sel_temp
    else:
        flex_n1 = None
        flex_slider = None
        op_n1 = base_n1
        op_slider = base_slider
        temp_used = oat

    return {
        "airport": info["airport"],
        "runway": info["runway"],

        "thrust_mode_raw": mode_raw,          # thrust profile name from SimBrief
        "thrust_mode_for_tables": mode_norm,  # MAX / TO1 / TO2 / FLEX

        "flaps": info["flaps"],
        "packs": info["bleeds"],
        "eng_anti_ice": info["anti_ice_for_calc"],

        "oat_C": oat,
        "sel_temp_C": sel_temp,
        "flex_active": flex_active,
        "temp_used_for_calc_C": temp_used,

        # Operational values (what to use in IF)
        "N1_percent": round(op_n1, 2) if op_n1 is not None else None,
        "IF_slider_percent": round(op_slider, 1) if op_slider is not None else None,

        # V-speeds
        "speeds": info["speeds"],   # { "V1": int|None, "VR": int|None, "V2": int|None }
    }
