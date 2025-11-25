# app.py

import re
from typing import Optional, Dict, Any

import streamlit as st
import streamlit.components.v1 as components


# N1 logic modules for each aircraft
from b737max8N1 import n1_and_slider as n1_and_slider_737
from b772erN1 import n1_and_slider_772
from a223N1 import n1_and_slider_a223
from a380N1 import n1_and_slider_a380


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

    # Normalize packs flag (used for some aircraft; ignored for others)
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
      - thrust mode contains 'D-TO' or 'FLEX'
      - SEL TEMP > OAT
    """
    if oat_C is None or sel_temp_C is None or mode_raw is None:
        return False
    if sel_temp_C <= oat_C:
        return False
    return ("D-TO" in mode_raw.upper()) or ("FLEX" in mode_raw.upper())


# =========================
# Aircraft-specific N1 dispatcher
# =========================

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


# =========================
# Aircraft detection
# =========================

def detect_aircraft(text: str) -> Optional[str]:
    """
    Detect aircraft from the TAKEOFF PERFORMANCE header line.

    Examples:
      N808SB B737 MAX 8 LEAP-1B28
      N755SB B777-200ER GE90-94B
      N388SB A380-800 TRENT 970-84
      C-GXXX A220-300 PW1524G
    """
    m = re.search(r"TAKEOFF PERFORMANCE\s*\n(.+)", text)
    if not m:
        return None
    header_line = m.group(1).upper().strip()

    # 737 MAX 8
    if "B737" in header_line and "MAX" in header_line and "8" in header_line:
        return "B737 MAX 8"

    # 777-200ER (B772)
    if ("B777" in header_line and "200" in header_line) or "B772" in header_line:
        return "B777-200ER"

    # A220-300 / BD-500-300 etc.
    if "A220-300" in header_line or "BD-500-300" in header_line or "A223" in header_line:
        return "A220-300"

    # A380-800
    if "A380-800" in header_line or "A388" in header_line:
        return "A380-800"

    # Extend here for more aircraft later
    return None


# =========================
# Visual components (HTML/CSS)
# =========================

def render_ecam_gauge(slider_percent: Optional[float], n1_percent: Optional[float]):
    if slider_percent is None or n1_percent is None:
        st.write("Gauge: N/A")
        return

    sp = max(0.0, min(100.0, float(slider_percent)))
    n1 = max(0.0, min(150.0, float(n1_percent)))

    # slider -> dial angle
    angle = sp / 100 * 180 - 90

    gauge_html = f"""
    <html>
    <head>
      <style>
        body {{
          margin: 0;
          padding: 0;
          background: transparent;
        }}

        .gauge-card {{
          background: #000;
          border-radius: 12px;
          padding: 12px 16px 20px 16px;
          display: inline-flex;
          align-items: flex-start;
          justify-content: center;
          gap: 14px;
          font-family: monospace;
        }}

        .thr-label {{
          color: #9be38c;
          font-size: 14px;
          text-align: center;
          line-height: 1.1;
          margin-top: 26px;
        }}

        .right-side {{
          display: flex;
          flex-direction: column;
          align-items: center;
        }}

        /* IF THROTTLE label */
        .if-label {{
          color: #ffffff90;
          font-size: 12px;
          margin-bottom: 6px;
          margin-top: 2px;
        }}

        /* perfect semicircle */
        .dial-wrapper {{
          position: relative;
          width: 140px;
          height: 90px;
        }}

        .dial {{
          position: absolute;
          left: 0;
          bottom: 0;
          width: 140px;
          height: 70px;
          border-radius: 140px 140px 0 0;
          border: 3px solid #cfcfcf;
          border-bottom: none;
          background: radial-gradient(circle at 50% 120%, #222 0%, #000 70%);
        }}

        /* extended needle */
        .needle {{
          position: absolute;
          bottom: 0;
          left: 50%;
          width: 3px;
          height: 82%;
          background: #6df36d;
          transform-origin: bottom center;
          transform: translateX(-50%) rotate({angle}deg);
          box-shadow: 0 0 4px rgba(0,0,0,0.7);
        }}

        /* ticks */
        .tick {{
          position: absolute;
          color: #f0f0f0;
          font-size: 12px;
        }}

        .tick0 {{ bottom: 2px; left: 8px; }}
        .tick5 {{ top: 4px; left: 50%; transform: translateX(-50%); }}
        .tick10 {{ bottom: 2px; right: 8px; }}

        /* N1 box + label */
        .n1-label {{
          margin-top: 6px;
          color: #ffffff90;
          font-size: 12px;
        }}

        .n1-box {{
          margin-top: 4px;
          width: 100px;
          height: 40px;
          border-radius: 6px;
          border: 2px solid #6df36d;
          background: #222;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 20px;
          color: #6df36d;
          box-shadow: 0 0 6px rgba(0,0,0,0.6);
        }}
      </style>
    </head>

    <body>
      <div class="gauge-card">

        <!-- left THR % label -->
        <div class="thr-label">
          THR<br>% 
        </div>

        <div class="right-side">

          <!-- IF SLIDER LABEL -->
          <div class="if-label">IF THROTTLE</div>

          <div class="dial-wrapper">
            <div class="dial">
              <div class="needle"></div>

              <div class="tick tick0">0</div>
              <div class="tick tick5">5</div>
              <div class="tick tick10">10</div>
            </div>
          </div>

          <!-- N1 DIGITAL LABEL -->
          <div class="n1-label">N1 %</div>

          <div class="n1-box">{n1:.1f}</div>

        </div>

      </div>
    </body>
    </html>
    """

    components.html(gauge_html, height=240)




def render_flaps_airbus(flaps_value: Optional[str]):
    """
    Airbus-style flap indicator (A220 / A380):
    ladder with S .... F and a green symbol + text (0, 1, 1+F, 2, 3, FULL)
    """
    if not flaps_value:
        st.write("Flaps: N/A")
        return

    flaps_str = str(flaps_value).upper()

    # Order of Airbus detents we care about visually
    detents = ["0", "1", "1+F", "2", "3", "FULL"]
    # map FULL to F for text on top line
    short_text = flaps_str.replace("FULL", "F")

    # find index for highlighting
    try:
        idx = detents.index(flaps_str)
    except ValueError:
        idx = 0

    # build little squares, highlight the selected one in green
    boxes_html = ""
    for i, d in enumerate(detents):
        if i == idx:
            boxes_html += (
                '<div style="width:10px;height:10px;border-radius:2px;'
                'border:2px solid #9be38c;background:#041;">'
                "</div>"
            )
        else:
            boxes_html += (
                '<div style="width:8px;height:8px;border-radius:2px;'
                'border:1px solid #eee;background:transparent;"></div>'
            )

    html = f"""
    <html>
    <head>
      <style>
        .airbus-flaps-card {{
          background:#000;
          border-radius:12px;
          padding:10px 14px;
          display:inline-flex;
          flex-direction:column;
          align-items:center;
          font-family:monospace;
          color:#fff;
        }}
        .airbus-top-row {{
          display:flex;
          justify-content:space-between;
          width:150px;
          font-size:12px;
          margin-bottom:2px;
        }}
        .airbus-ladder {{
          display:flex;
          justify-content:space-between;
          align-items:center;
          width:150px;
          margin-bottom:4px;
        }}
        .airbus-mode {{
          margin-top:2px;
          font-size:16px;
          color:#9be38c;
        }}
      </style>
    </head>
    <body style="margin:0;padding:0;background:transparent;">
      <div class="airbus-flaps-card">
        <div class="airbus-top-row">
          <span>S</span>
          <span>F</span>
        </div>
        <div class="airbus-ladder">
          {boxes_html}
        </div>
        <div class="airbus-mode">{flaps_str}</div>
      </div>
    </body>
    </html>
    """
    components.html(html, height=120)

def render_flaps_b777(flaps_value: Optional[str]):
    """
    777-style vertical flaps tape.
    SimBrief values: 0, 1, 5, 15, 20, 25, 30
    """
    if flaps_value is None:
        st.write("Flaps: N/A")
        return

    try:
        val = float(flaps_value)
    except ValueError:
        val = 0.0

    detents = [0, 1, 5, 15, 20, 25, 30]
    v_min, v_max = min(detents), max(detents)
    frac = (val - v_min) / (v_max - v_min) if v_max > v_min else 0.0
    frac = max(0.0, min(1.0, frac))

    html = f"""
    <html>
    <head>
      <style>
        .b777-card {{
          background:#000;
          border-radius:12px;
          padding:10px 16px;
          display:inline-flex;
          align-items:center;
          justify-content:center;
          font-family:monospace;
        }}
        .b777-label {{
          color:#00f7ff;
          font-size:14px;
          margin-right:8px;
          letter-spacing:2px;
        }}
        .b777-container {{
          position:relative;
          width:60px;
          height:150px;
          border:2px solid #888;
          background:#111;
          display:flex;
          align-items:flex-end;
          justify-content:center;
          box-shadow:0 0 6px rgba(0,0,0,0.7);
        }}
        .b777-green-bar {{
          position:absolute;
          left:0;
          right:0;
          height:4px;
          background:#6df36d;
          bottom:{frac*100:.1f}%;
        }}
        .b777-value {{
          position:absolute;
          right:-40px;
          bottom:{frac*100:.1f}%;
          color:#6df36d;
          font-size:18px;
          transform:translateY(50%);
        }}
      </style>
    </head>
    <body style="margin:0;padding:0;background:transparent;">
      <div class="b777-card">
        <div class="b777-label">
          F<br>L<br>A<br>P<br>S
        </div>
        <div class="b777-container">
          <div class="b777-green-bar"></div>
          <div class="b777-value">{val:g}</div>
        </div>
      </div>
    </body>
    </html>
    """
    components.html(html, height=190)

def render_flaps_737max(flaps_value: Optional[str]):
    """
    737 MAX-style flap dial.
    SimBrief values: 0, 1, 2, 5, 10, 15, 25, 30, 40
    """
    if flaps_value is None:
        st.write("Flaps: N/A")
        return

    flaps_str = str(flaps_value).strip().upper()

    detents = ["0", "1", "2", "5", "10", "15", "25", "30", "40"]

    # Manually tuned angles to roughly match a real 737 dial (deg, clockwise)
    angle_map = {
        "0":  -115,
        "1":   -85,
        "2":   -60,
        "5":   -30,
        "10":    0,
        "15":   30,
        "25":   55,
        "30":   80,
        "40":  105
    }

    # Fallback to 0 if unknown
    needle_angle = angle_map.get(flaps_str, angle_map["0"])

    # Build ticks & labels using the same angles
    ticks_html = ""
    for label in detents:
        a = angle_map[label]

        ticks_html += f"""
        <!-- tick {label} -->
        <div class="b737-tick"
             style="transform:translate(-50%, -50%) rotate({a}deg) translate(0, -70px);">
        </div>

        <!-- label {label} -->
        <div class="b737-num"
             style="transform:translate(-50%, -50%) rotate({a}deg) translate(0, -88px) rotate({-a}deg);">
          {label}
        </div>
        """

    html = f"""
    <html>
    <head>
      <style>
        body {{
          margin:0;
          padding:0;
          background:transparent;
        }}

        .b737-card {{
          background:#000;
          border-radius:16px;
          padding:12px;
          display:inline-flex;
          flex-direction:column;
          align-items:center;
          font-family:monospace;
          color:#fff;
        }}

        .b737-dial {{
          position:relative;
          width:180px;
          height:180px;
          border-radius:50%;
          border:4px solid #888;
          background:#111;
          margin-bottom:6px;
        }}

        .b737-tick {{
          position:absolute;
          top:50%;
          left:50%;
          width:2px;
          height:10px;
          background:#fff;
          transform-origin:bottom center;
        }}

        .b737-num {{
          position:absolute;
          top:50%;
          left:50%;
          color:#fff;
          font-size:11px;
          transform-origin:center;
        }}

        .b737-needle {{
          position:absolute;
          top:50%;
          left:50%;
          width:70px;
          height:3px;
          background:#ffffff;
          transform-origin:left center;
          transform:translate(-50%, -50%) rotate({needle_angle}deg);
        }}

        .b737-center {{
          position:absolute;
          top:50%;
          left:50%;
          width:18px;
          height:18px;
          border-radius:50%;
          background:#000;
          border:2px solid #888;
          transform:translate(-50%,-50%);
        }}

        .b737-label-bottom {{
          margin-top:4px;
          font-size:13px;
          letter-spacing:1px;
          color:#ddd;
        }}
      </style>
    </head>
    <body>
      <div class="b737-card">
        <div class="b737-dial">
          {ticks_html}
          <div class="b737-needle"></div>
          <div class="b737-center"></div>
        </div>
        <div class="b737-label-bottom">FLAPS&nbsp;&nbsp;{flaps_str}</div>
      </div>
    </body>
    </html>
    """

    components.html(html, height=230)




# =========================
# Streamlit UI
# =========================

def main():
    st.title("SimBrief ➜ Infinite Flight Takeoff N1")

    st.write(
        "Paste your **SimBrief TAKEOFF PERFORMANCE** section below.\n\n"
        "Currently supported aircraft:\n"
        "- **B737 MAX 8**\n"
        "- **B777-200ER**\n"
        "- **A220-300 (A223)**\n"
        "- **A380-800 (GP7270)**\n\n"
        "For supported aircraft, this tool computes:\n"
        "- Operational N1 and Infinite Flight power slider\n"
        "- Flap setting and thrust profile (e.g. D-TO1 / D-TO2 / FLEX)\n"
        "- V1 / VR / V2 speeds from SimBrief\n\n"
        "Note: For the A380-800 we always assume **MAX takeoff (MTO)**, "
        "even if SimBrief outputs FLEX or a derate."
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

        if aircraft in {"B737 MAX 8", "B777-200ER", "A220-300", "A380-800"}:
            st.success(f"Detected aircraft: {aircraft}")

            try:
                result = compute_takeoff_from_simbrief(simbrief_text, aircraft)
            except Exception as e:
                st.error(f"Error computing N1: {e}")
                return

            # === Row 1: Operational takeoff setting (numeric) ===
            st.subheader("Operational Takeoff Setting")
            row1_col1, row1_col2, row1_col3 = st.columns(3)
            with row1_col1:
                n1_val = result['N1_percent']
                st.metric("N1 (Operational)", f"{n1_val:.2f} %" if n1_val is not None else "N/A")
            with row1_col2:
                s_val = result['IF_slider_percent']
                st.metric("IF Power Slider", f"{s_val:.1f} %" if s_val is not None else "N/A")
            with row1_col3:
                st.metric("Flaps", result.get("flaps") or "N/A")

            # === Row 2: Thrust profile + V-speeds ===
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

            # === Row 3: Visual overview ===
            st.subheader("Visual Takeoff Overview")
            vcol1, vcol2 = st.columns(2)

            with vcol1:
                st.caption("Engine Thrust Gauge (ECAM style)")
                render_ecam_gauge(result['IF_slider_percent'], result['N1_percent'])


            with vcol2:
                st.caption("Flaps Configuration")

                flaps_val = result.get("flaps")

                if aircraft in {"A220-300", "A380-800"}:
                    render_flaps_airbus(flaps_val)
                elif aircraft == "B777-200ER":
                    render_flaps_b777(flaps_val)
                elif aircraft == "B737 MAX 8":
                    render_flaps_737max(flaps_val)
                else:
                    st.write(flaps_val or "N/A")


        else:
            st.warning(
                "This SimBrief text does not appear to be for a supported aircraft "
                "(B737 MAX 8, B777-200ER, A220-300, A380-800).\n\n"
                "Support for additional aircraft is in progress and "
                "will be added in the future."
            )


if __name__ == "__main__":
    main()
