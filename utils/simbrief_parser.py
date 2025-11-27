# utils/simbrief_parser.py

import re
from typing import Optional, Dict, Any


def parse_field(pattern: str, text: str, cast=str, default=None, flags=0):
    m = re.search(pattern, text, flags)
    if not m:
        return default
    val = m.group(1).strip()
    try:
        return cast(val)
    except Exception:
        return val


def parse_thrust_mode(text: str) -> Optional[str]:
    """
    Prefer THRUST from the OUTPUTS block; fall back to first THRUST line.
    """
    m = re.search(r"OUTPUTS:([\s\S]*?)\n\n", text)
    if m:
        block = m.group(1)
        m2 = re.search(r"\bTHRUST\s+([A-Z0-9\-]+)", block)
        if m2:
            return m2.group(1).strip()

    m = re.search(r"\bTHRUST\s+([A-Z0-9\-]+)", text)
    return m.group(1).strip() if m else None


def parse_flaps_from_outputs(text: str) -> Optional[str]:
    """
    Grab FLAPS from OUTPUTS (not INPUTS).
    Example: 'FLAPS         5     V1  148'
    """
    m = re.search(r"OUTPUTS:([\s\S]*?)(?:MESSAGES:|$)", text)
    if not m:
        return None
    block = m.group(1)

    m2 = re.search(r"\bFLAPS\s+([A-Z0-9+FULLf]+)", block, re.IGNORECASE)
    return m2.group(1).strip().upper() if m2 else None


def parse_speeds_from_outputs(text: str) -> Dict[str, Optional[int]]:
    """
    Parse V1, VR, V2 from the OUTPUTS block.
    """
    v1 = vr = v2 = None
    m = re.search(r"OUTPUTS:([\s\S]*?)(?:MESSAGES:|$)", text)
    if m:
        block = m.group(1)
        m_v1 = re.search(r"\bV1\s+(\d+)", block)
        m_vr = re.search(r"\bVR\s+(\d+)", block)
        m_v2 = re.search(r"\bV2\s+(\d+)", block)
        if m_v1:
            v1 = int(m_v1.group(1))
        if m_vr:
            vr = int(m_vr.group(1))
        if m_v2:
            v2 = int(m_v2.group(1))
    return {"V1": v1, "VR": vr, "V2": v2}


def parse_simbrief_takeoff_block(text: str) -> Dict[str, Any]:
    """
    Parses SimBrief takeoff performance section into a dict.
    """
    airport = parse_field(r"APT\s+([A-Z0-9]{4})", text)
    runway = parse_field(r"RWY\s+(\S+)", text)

    oat = parse_field(r"OAT\s+([\-]?\d+)", text, int)
    elev_ft = parse_field(r"ELEV\s+(\d+)", text, int)

    # BLEEDS / AICE in INPUTS
    bleeds_in = parse_field(r"INPUTS:[\s\S]*?BLEEDS\s+(ON|OFF|AUTO)", text)
    aice_in = parse_field(r"INPUTS:[\s\S]*?A/ICE\s+([A-Z]+)", text)

    # BLEEDS / AICE in OUTPUTS (more authoritative)
    bleeds_out = parse_field(r"RWY LIM\s+[0-9.]+\s+BLEEDS\s+(ON|OFF)", text)
    aice_out = parse_field(r"LIM CODE\s+\S+\s+A/ICE\s+([A-Z]+)", text)

    bleeds = (bleeds_out or bleeds_in or "AUTO").upper()
    aice_raw = (aice_out or aice_in or "AUTO").upper()

    # Interpret A/ICE: engine anti-ice on for ENG/ALL/ON/ENG+WING
    eng_anti_ice = aice_raw in {"ON", "ALL", "ENG", "ENG+WING"}

    thrust_mode_str = parse_thrust_mode(text)
    sel_temp = parse_field(r"SEL TEMP\s+(\d+)", text, int)

    flaps_out = parse_flaps_from_outputs(text)
    speeds = parse_speeds_from_outputs(text)

    # Normalize thrust mode into MAX / TO1 / TO2 / FLEX-type
    mode_norm = "MAX"
    if thrust_mode_str:
        t = thrust_mode_str.upper()
        if "TO2" in t:
            mode_norm = "TO2"
        elif "TO1" in t:
            mode_norm = "TO1"
        elif "FLEX" in t:
            mode_norm = "FLEX"
        elif t in {"D-TO", "DTO"}:
            mode_norm = "MAX"
        else:
            mode_norm = "MAX"

    # Normalize packs flag
    packs_for_calc = "on" if bleeds == "ON" else "off" if bleeds == "OFF" else "on"

    return {
        "airport": airport,
        "runway": runway,
        "oat_C": oat,
        "elevation_ft": elev_ft,
        "mode_raw": thrust_mode_str,        # e.g. 'D-TO2', 'FLEX'
        "mode_normalized": mode_norm,       # 'MAX' | 'TO1' | 'TO2' | 'FLEX'
        "bleeds": bleeds,                   # ON/OFF/AUTO
        "packs_for_calc": packs_for_calc,   # 'on' | 'off'
        "aice_raw": aice_raw,               # e.g. 'ENG'
        "anti_ice_for_calc": eng_anti_ice,  # bool
        "sel_temp_C": sel_temp,
        "flaps": flaps_out,                 # e.g. '5', '1+F'
        "speeds": speeds,                   # dict with V1, VR, V2
    }


def is_flex_active(
    oat_C: Optional[int],
    sel_temp_C: Optional[int],
    mode_raw: Optional[str],
) -> bool:
    """
    FLEX active if:
      - thrust mode contains 'D-TO' or 'FLEX'
      - SEL TEMP > OAT
    """
    if oat_C is None or sel_temp_C is None or mode_raw is None:
        return False
    if sel_temp_C <= oat_C:
        return False
    return ("D-TO" in mode_raw.upper()) or ("FLEX" in mode_raw.upper())


def detect_aircraft(text: str) -> Optional[str]:
    """
    Detect aircraft from the TAKEOFF PERFORMANCE header line.

    Examples:
      N808SB B737 MAX 8 LEAP-1B28
      9V-MBE BOEING 737-8 MAX LEAP-1B28
      N755SB B777-200ER GE90-94B
      N388SB A380-800 TRENT 970-84
      C-GXXX A220-300 PW1524G
    """
    m = re.search(r"TAKEOFF PERFORMANCE\s*\n(.+)", text, re.IGNORECASE)
    if not m:
        return None
    header_line = m.group(1).upper().strip()

    # 737 MAX 8: catch both "B737 MAX 8" and "BOEING 737-8 MAX"
    if ("737" in header_line and "MAX" in header_line and
            (" 8" in header_line or "-8" in header_line)):
        return "B737 MAX 8"

    # 777-200ER (B772)
    if ("777" in header_line and "200" in header_line) or "B772" in header_line:
        return "B777-200ER"

    # A220-300 / BD-500-300 / A223 / BCS3
    if ("A220-300" in header_line or "BD-500-300" in header_line or
            "A223" in header_line or "BCS3" in header_line):
        return "A220-300"

    # A380-800 / A388
    if "A380-800" in header_line or "A388" in header_line or "A380" in header_line:
        return "A380-800"

    # Extend here for more aircraft later
    return None
