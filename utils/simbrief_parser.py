import re
from typing import Dict, Any, Optional

def parse_field(pattern: str, text: str, cast=str, default=None):
    m = re.search(pattern, text)
    if not m:
        return default
    try:
        return cast(m.group(1).strip())
    except:
        return m.group(1).strip()

def parse_thrust_mode(text: str):
    m = re.search(r"OUTPUTS:([\s\S]*?)\n\n", text)
    if m:
        out_block = m.group(1)
        m2 = re.search(r"THRUST\s+([A-Z0-9\-]+)", out_block)
        if m2:
            return m2.group(1)
    m = re.search(r"\bTHRUST\s+([A-Z0-9\-]+)", text)
    return m.group(1) if m else None

def parse_flaps(text: str):
    m = re.search(r"OUTPUTS:([\s\S]*?)(?:MESSAGES:|$)", text)
    if not m:
        return None
    block = m.group(1)
    m2 = re.search(r"FLAPS\s+([A-Z0-9]+)", block)
    return m2.group(1) if m2 else None

def parse_trim(text: str):
    m = re.search(r"STAB\s+TRIM\s+([0-9.]+\s*(?:UP|DN|DOWN)?)", text, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\bTRIM\s+([0-9.]+\s*(?:UP|DN|DOWN)?)", text, re.I)
    return m.group(1) if m else None

def simbrief_extract(text: str) -> Dict[str, Any]:
    return {
        "airport": parse_field(r"APT\s+([A-Z]{4})", text),
        "runway": parse_field(r"RWY\s+(\S+)", text),
        "oat_C": parse_field(r"OAT\s+([\-]?\d+)", text, int),
        "elevation_ft": parse_field(r"ELEV\s+(\d+)", text, int),
        "thrust_mode_raw": parse_thrust_mode(text),
        "sel_temp_C": parse_field(r"SEL TEMP\s+(\d+)", text, int),
        "flaps": parse_flaps(text),
        "trim_raw": parse_trim(text),
        "bleeds": parse_field(r"BLEEDS\s+(ON|OFF|AUTO)", text),
        "aice_raw": parse_field(r"A/ICE\s+([A-Z]+)", text), 
    }
