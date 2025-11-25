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


def parse_trim(text: str) -> Optional[str]:
    """
    Try to parse trim / stab trim.
      STAB TRIM    5.0 UP
      TRIM         4.5UP
    Returns a raw string like '5.0 UP' or '4.5UP'.
    """
    m = re.search(
        r"STAB\s+TRIM\s+([0-9.]+\s*(?:UP|DN|DOWN)?)",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    m = re.search(
        r"\bTRIM\s+([0-9.]+\s*(?:UP|DN|DOWN)?)",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    return None


def parse_simbrief_takeoff_block(text: str) -> Dict[str, Any]:
    """
    Parses SimBrief takeoff performance section, including:
      - airport, runway, elevation, OAT
      - thrust mode (raw + normalized for tables)
      - BLEEDS / A/ICE (and packs/anti-ice flags for calc)
      - flaps (from OUTPUTS)
      - trim (if present)
      - SEL TEMP (for FLEX logic)
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
    trim_raw = parse_trim(text)

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
        "trim_raw": trim_raw,               # e.g. '5.0 UP'
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
      - base (OAT, no FLEX) N1 + slider
      - flex (SEL TEMP, if active) N1 + slider
      - which one is actually used (SimBrief's D-TO logic)
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
    else:
        flex_n1 = None
        flex_slider = None

    # 3) Operational (what you actually set)
    if flex_active:
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

        "thrust_mode_raw": mode_raw,
        "thrust_mode_for_tables": mode_norm,

        "flaps": info["flaps"],
        "trim": info["trim_raw"],

        "packs": packs,
        "eng_anti_ice": eng_aice,

        "oat_C": oat,
        "sel_temp_C": sel_temp,
        "flex_active": flex_active,
        "temp_used_for_calc_C": temp_used,

        "base": {
            "temp_C": oat,
            "N1_percent": round(base_n1, 2),
            "IF_slider_percent": round(base_slider, 1),
        },
        "flex": {
            "temp_C": sel_temp if flex_active else None,
            "N1_percent": round(flex_n1, 2) if flex_active else None,
            "IF_slider_percent": round(flex_slider, 1) if flex_active else None,
        },

        "N1_percent": round(op_n1, 2),
        "IF_slider_percent": round(op_slider, 1),
    }


# =========================
# Aircraft detection
# =========================

def detect_aircraft(text: str) -> Optional[str]:
    """
    Very simple aircraft detection from the header line, e.g.:
      N808SB B737 MAX 8 LEAP-1B28
    Returns 'B737 MAX 8' or None.
    """
    m = re.search(r"TAKEOFF PERFORMANCE\s*\n(.+)", text)
    if not m:
        return None
    header_line = m.group(1).strip()

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
        "Paste your **SimBrief TAKEOFF PERFORMANCE** section below. "
        "If the aircraft is detected as **B737 MAX 8**, this tool will compute:\n"
        "- Base (non-FLEX) N1 and IF power\n"
        "- FLEX N1 and IF power (if applicable)\n"
        "- Operational setting you should use in Infinite Flight."
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

            # High-level summary
            st.subheader("Operational Takeoff Setting")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("N1 (Operational)", f"{result['N1_percent']} %")
                st.metric("IF Power Slider", f"{result['IF_slider_percent']} %")
            with col2:
                st.metric("Flaps", result.get("flaps") or "N/A")
                st.metric("Trim", result.get("trim") or "N/A")

            # Base vs FLEX
            st.subheader("Base vs FLEX Comparison")

            base = result["base"]
            flex = result["flex"]

            c1, c2 = st.columns(2)

            with c1:
                st.markdown("**Base (no FLEX)** – using actual OAT")
                st.write(f"Temperature: {base['temp_C']} °C")
                st.write(f"N1: **{base['N1_percent']} %**")
                st.write(f"IF Slider: **{base['IF_slider_percent']} %**")

            with c2:
                st.markdown("**FLEX (Assumed Temp)**")
                if result["flex_active"]:
                    st.write(f"SEL TEMP: {flex['temp_C']} °C")
                    st.write(f"N1: **{flex['N1_percent']} %**")
                    st.write(f"IF Slider: **{flex['IF_slider_percent']} %**")
                else:
                    st.write("FLEX not active (no D-TO or SEL TEMP ≤ OAT).")

            # Extra details
            st.subheader("Details")
            st.json({
                "airport": result["airport"],
                "runway": result["runway"],
                "thrust_mode_raw": result["thrust_mode_raw"],
                "thrust_mode_for_tables": result["thrust_mode_for_tables"],
                "packs": result["packs"],
                "eng_anti_ice": result["eng_anti_ice"],
                "oat_C": result["oat_C"],
                "sel_temp_C": result["sel_temp_C"],
                "temp_used_for_calc_C": result["temp_used_for_calc_C"],
            })

        else:
            st.warning(
                "This SimBrief text does not appear to be for a **B737 MAX 8**.\n\n"
                "Support for additional aircraft is currently in progress and "
                "will be added in the future."
            )


if __name__ == "__main__":
    main()
