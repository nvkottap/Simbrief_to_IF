# app.py

import re
from typing import Optional, Dict, Any

import streamlit as st

# 737 MAX 8 N1 logic (your module)
from b737max8N1 import n1_and_slider


# =========================
# Parsing helpers
# =========================

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

    m2 = re.search(r"\bFLAPS\s+([A-Z0-9]+)", block)
    return m2.group(1).strip() if m2 else None


def parse_speeds_from_outputs(text: str) -> Dict[str, Optional[int]]:
    """
    Parse V1, VR, V2 from the OUTPUTS block.
    Example lines:
       FLAPS         5     V1          148
       THRUST     D-TO1    VR          149
       SEL TEMP     46     V2          156
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
    Parses SimBrief takeoff performance section, including:
      - airport, runway, elevation, OAT
      - thrust mode (raw + normalized for tables)
      - BLEEDS / A/ICE (and packs/anti-ice flags for calc)
      - flaps (from OUTPUTS)
      - SEL TEMP (for FLEX logic)
      - V1 / VR / V2 (from OUTPUTS)
    """
    airport = parse_field(r"APT\s+([A-Z]{4})", text)
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

    # Interpret A/ICE:
    #  - ON / ALL / ENG / ENG+WING => engine anti-ice ON
    eng_anti_ice = False
    if aice_raw in {"ON", "ALL", "ENG", "ENG+WING"}:
        eng_anti_ice = True

    thrust_mode_str = parse_thrust_mode(text)
    sel_temp = parse_field(r"SEL TEMP\s+(\d+)", text, int)

    flaps_out = parse_flaps_from_outputs(text)
    speeds = parse_speeds_from_outputs(text)

    # Normalize thrust mode into MAX / TO1 / TO2 for N1 tables
    mode_norm = "MAX"
    if thrust_mode_str:
        t = thrust_mode_str.upper()
        if "TO1" in t:
            mode_norm = "TO1"
        elif "TO2" in t:
            mode_norm = "TO2"
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
        "mode_raw": thrust_mode_str,        # e.g. 'D-TO1'
        "mode_normalized": mode_norm,       # 'MAX' | 'TO1' | 'TO2'
        "bleeds": bleeds,                   # ON/OFF/AUTO
        "packs_for_calc": packs_for_calc,   # 'on' | 'off'
        "aice_raw": aice_raw,               # e.g. 'ENG'
        "anti_ice_for_calc": eng_anti_ice,  # bool
        "sel_temp_C": sel_temp,
        "flaps": flaps_out,                 # e.g. '5'
        "speeds": speeds,                   # dict with V1, VR, V2
    }


def is_flex_active(
    oat_C: Optional[int],
    sel_temp_C: Optional[int],
    mode_raw: Optional[str],
) -> bool:
    """
    FLEX active if:
      - thrust mode contains 'D-TO'
      - SEL TEMP > OAT
    """
    if oat_C is None or sel_temp_C is None or mode_raw is None:
        return False
    if sel_temp_C <= oat_C:
        return False
    return "D-TO" in mode_raw.upper()


def compute_takeoff_from_simbrief(text: str) -> Dict[str, Any]:
    """
    Returns:
      - operational N1 + slider (base or FLEX, depending on SimBrief)
      - flaps, thrust profile name, and V-speeds
    """
    info = parse_simbrief_takeoff_block(text)

    oat = info["oat_C"]
    sel_temp = info["sel_temp_C"]
    mode_raw = info["mode_raw"]              # e.g. 'D-TO1'
    mode_norm = info["mode_normalized"]      # 'MAX' | 'TO1' | 'TO2'
    elev_ft = info["elevation_ft"]
    packs = info["packs_for_calc"]           # 'on' | 'off'
    eng_aice = info["anti_ice_for_calc"]     # bool

    # 1) Base N1 at actual OAT (no FLEX)
    base_n1, base_slider = n1_and_slider(
        mode_norm,
        elev_ft,
        oat,
        packs=packs,
        eng_anti_ice=eng_aice,
    )

    # 2) FLEX N1 at SEL TEMP (if active)
    flex_active = is_flex_active(oat, sel_temp, mode_raw)

    if flex_active:
        flex_n1, flex_slider = n1_and_slider(
            mode_norm,
            elev_ft,
            sel_temp,
            packs=packs,
            eng_anti_ice=eng_aice,
        )
        op_n1 = flex_n1
        op_slider = flex_slider
        temp_used = sel_temp
    else:
        op_n1 = base_n1
        op_slider = base_slider
        temp_used = oat

    return {
        "airport": info["airport"],
        "runway": info["runway"],

        "thrust_mode_raw": mode_raw,          # thrust profile name from SimBrief
        "thrust_mode_for_tables": mode_norm,  # MAX / TO1 / TO2

        "flaps": info["flaps"],
        "packs": packs,
        "eng_anti_ice": eng_aice,

        "oat_C": oat,
        "sel_temp_C": sel_temp,
        "flex_active": flex_active,
        "temp_used_for_calc_C": temp_used,

        # Operational values (what to use in IF)
        "N1_percent": round(op_n1, 2),
        "IF_slider_percent": round(op_slider, 1),

        # V-speeds
        "speeds": info["speeds"],   # { "V1": int|None, "VR": int|None, "V2": int|None }
    }


# =========================
# Aircraft detection
# =========================

def detect_aircraft(text: str) -> Optional[str]:
    """
    Detect aircraft from the TAKEOFF PERFORMANCE header line.
    """
    m = re.search(r"TAKEOFF PERFORMANCE\s*\n(.+)", text)
    if not m:
        return None
    header_line = m.group(1).upper().strip()

    if "B737" in header_line and "MAX" in header_line and "8" in header_line:
        return "B737 MAX 8"

    # (Extend here for other aircraft in the future)
    return None


# =========================
# Streamlit UI
# =========================

def main():
    st.title("SimBrief ➜ Infinite Flight Takeoff N1 (B737 MAX 8)")

    st.write(
        "Paste your **SimBrief TAKEOFF PERFORMANCE** section below.\n\n"
        "If the aircraft is detected as **B737 MAX 8**, this tool will compute:\n"
        "- Operational N1 and Infinite Flight power slider\n"
        "- Flap setting and thrust profile (e.g. D-TO1)\n"
        "- V1 / VR / V2 speeds from SimBrief"
    )

    simbrief_text = st.text_area(
        "SimBrief Takeoff Performance Text",
        height=350,
        placeholder="Paste the SimBrief TAKEOFF PERFORMANCE block here...",
    )

    if st.button("Compute Takeoff Thrust"):
        if not simbrief_text.strip():
            st.warning("Please paste SimBrief text first.")
            return

        aircraft = detect_aircraft(simbrief_text)

        if aircraft == "B737 MAX 8":
            st.success(f"Detected aircraft: {aircraft}")

            try:
                result = compute_takeoff_from_simbrief(simbrief_text)
            except Exception as e:
                st.error(f"Error computing N1: {e}")
                return

            # === Row 1: Operational takeoff setting ===
            st.subheader("Operational Takeoff Setting")
            row1_col1, row1_col2, row1_col3 = st.columns(3)
            with row1_col1:
                st.metric("N1 (Operational)", f"{result['N1_percent']} %")
            with row1_col2:
                st.metric("IF Power Slider", f"{result['IF_slider_percent']} %")
            with row1_col3:
                st.metric("Flaps", result.get("flaps") or "N/A")

            # === Row 2: Thrust profile + V-speeds (same style & size) ===
            st.subheader("Thrust Profile & V-Speeds")

            speeds = result.get("speeds", {})
            v1 = speeds.get("V1")
            vr = speeds.get("VR")
            v2 = speeds.get("V2")

            row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
            with row2_col1:
                st.metric("Thrust Profile", result.get("thrust_mode_raw") or "N/A")
            with row2_col2:
                st.metric("V1", f"{v1} kt" if v1 is not None else "N/A")
            with row2_col3:
                st.metric("VR", f"{vr} kt" if vr is not None else "N/A")
            with row2_col4:
                st.metric("V2", f"{v2} kt" if v2 is not None else "N/A")

        else:
            st.warning(
                "This SimBrief text does not appear to be for a **B737 MAX 8**.\n\n"
                "Support for additional aircraft is currently in progress and "
                "will be added in the future."
            )


if __name__ == "__main__":
    main()
