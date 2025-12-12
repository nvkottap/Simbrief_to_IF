import html
from typing import Any, Dict, Optional

import requests
import streamlit as st

from utils.simbrief_parser import (
    detect_aircraft_from_json,
    parse_takeoff_from_json,
    parse_ofp_overview_from_json,
    SimBriefTLRError,
)
from utils.n1_dispatcher import compute_takeoff_from_info
from utils.metar_decode import decode_metar


# -----------------------------
# Session state init
# -----------------------------
if "ofp" not in st.session_state:
    st.session_state["ofp"] = None
if "info" not in st.session_state:
    st.session_state["info"] = None
if "aircraft" not in st.session_state:
    st.session_state["aircraft"] = None
if "username" not in st.session_state:
    st.session_state["username"] = ""
if "unit_mode" not in st.session_state:
    st.session_state["unit_mode"] = "Auto"


# -----------------------------
# Page + theme CSS
# -----------------------------
st.set_page_config(page_title="SimBrief → IF Takeoff Helper", page_icon="✈️", layout="wide")

st.markdown(
    """
    <style>
    .if-card {
        background-color: #0f172a;
        border-radius: 0.75rem;
        padding: 0.75rem 1rem;
        border: 1px solid #1f2937;
        margin-bottom: 0.55rem;
    }
    .if-card-title {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9ca3af;
        margin-bottom: 0.1rem;
    }
    .if-card-value {
        font-size: 1.4rem;
        font-weight: 650;
        color: #f9fafb;
        margin-bottom: 0.15rem;
    }
    .if-card-sub {
        font-size: 0.85rem;
        color: #d1d5db;
        line-height: 1.25;
    }
    .if-chip {
        display: inline-block;
        padding: 0.15rem 0.45rem;
        border-radius: 999px;
        font-size: 0.70rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        background-color: #111827;
        color: #e5e7eb;
        margin-bottom: 0.25rem;
    }
    .if-chip-blue { background-color: #1d4ed8; color: #eff6ff; }
    .if-chip-orange { background-color: #c2410c; color: #fff7ed; }

    .if-body {
        color: #e5e7eb;
        font-size: 0.95rem;
        line-height: 1.4;
        white-space: pre-line;
    }
    .if-pre {
        background: #0b1220;
        border: 1px solid #1f2937;
        border-radius: 0.6rem;
        padding: 0.7rem 0.8rem;
        color: #e5e7eb;
        overflow-x: auto;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.9rem;
        white-space: pre-wrap;
        word-break: break-word;
        margin-top: 0.35rem;
    }

    /* compact radio label */
    div[data-testid="stRadio"] > label { display:none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


# -----------------------------
# SimBrief fetch (JSON)
# -----------------------------
def fetch_simbrief_ofp_json(username: str) -> Dict[str, Any]:
    base_url = "https://www.simbrief.com/api/xml.fetcher.php"
    params = {"username": username, "json": "v2"}

    resp = requests.get(base_url, params=params, timeout=25)

    if resp.status_code in (400, 404):
        raise RuntimeError(
            f"SimBrief returned HTTP {resp.status_code}. "
            "Double-check the username and make sure you generated a recent OFP."
        )

    resp.raise_for_status()

    try:
        ofp = resp.json()
    except Exception:
        raise RuntimeError(f"SimBrief did not return JSON. Response preview:\n{resp.text[:800]}")

    if not isinstance(ofp, dict):
        raise RuntimeError("SimBrief JSON root is not a dict.")

    return ofp


# -----------------------------
# UI helpers
# -----------------------------
def card(title: str, value: str, sub: str = ""):
    st.markdown(
        f"""
        <div class="if-card">
          <div class="if-card-title">{_esc(title)}</div>
          <div class="if-card-value">{_esc(value)}</div>
          <div class="if-card-sub">{_esc(sub)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _to_float(val: Any) -> Optional[float]:
    if val is None or val == {}:
        return None
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip().replace(",", "")
        return float(s)
    except Exception:
        return None


def _convert_mass(value: Optional[float], from_unit: str, to_unit: str) -> Optional[float]:
    if value is None:
        return None
    fu = (from_unit or "").lower()
    tu = (to_unit or "").lower()
    if fu == tu:
        return value
    if fu == "kg" and tu == "lb":
        return value * 2.2046226218
    if fu == "lb" and tu == "kg":
        return value / 2.2046226218
    return value


def _fmt_mass(val: Optional[float], unit: str) -> str:
    if val is None:
        return "N/A"
    return f"{val:,.0f} {unit}"


# -----------------------------
# Main pipeline
# -----------------------------
def run_takeoff_pipeline(info: Dict[str, Any], aircraft: str):
    # -------------------------
    # Flight Overview
    # -------------------------
    st.subheader("Flight Overview")

    origin = info.get("origin")
    origin_name = info.get("origin_name")
    destination = info.get("destination")
    destination_name = info.get("destination_name")

    dep_runway = info.get("dep_runway")
    dep_len = info.get("dep_runway_length_ft")
    dep_elev = info.get("dep_elev_ft")

    arr_runway = info.get("arr_runway")
    arr_len = info.get("arr_runway_length_ft")
    arr_elev = info.get("arr_elev_ft")

    route_str = info.get("route_string")

    orig_metar = info.get("orig_metar")
    dest_metar = info.get("dest_metar")

    c_dep, c_arr = st.columns(2)

    with c_dep:
        st.markdown('<div class="if-chip if-chip-blue">Departure</div>', unsafe_allow_html=True)

        dep_title = origin or "N/A"
        if origin and origin_name:
            dep_title = f"{origin} – {origin_name}"

        runway_line = f"<div><b>Runway:</b> {_esc(dep_runway)}</div>" if dep_runway else ""
        details = []
        if dep_elev is not None:
            details.append(f"Elevation: {dep_elev:.0f} ft")
        if dep_len is not None:
            details.append(f"Length: {dep_len:.0f} ft")
        details_line = f"<div>{_esc(' · '.join(details))}</div>" if details else ""

        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-value">{_esc(dep_title)}</div>
              <div class="if-body">
                {runway_line}
                {details_line}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c_arr:
        st.markdown('<div class="if-chip if-chip-orange">Arrival</div>', unsafe_allow_html=True)

        arr_title = destination or "N/A"
        if destination and destination_name:
            arr_title = f"{destination} – {destination_name}"

        runway_line = f"<div><b>Runway:</b> {_esc(arr_runway)}</div>" if arr_runway else ""
        details = []
        if arr_elev is not None:
            details.append(f"Elevation: {arr_elev:.0f} ft")
        if arr_len is not None:
            details.append(f"Length: {arr_len:.0f} ft")
        details_line = f"<div>{_esc(' · '.join(details))}</div>" if details else ""

        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-value">{_esc(arr_title)}</div>
              <div class="if-body">
                {runway_line}
                {details_line}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    card("Aircraft", aircraft, "Detected from SimBrief OFP")

    if route_str:
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">Route</div>
              <div class="if-pre">{_esc(route_str)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------------------------
    # Payload & Fuel (+ Units control)
    # -------------------------
    left, right = st.columns([0.72, 0.28])
    with left:
        st.subheader("Payload & Fuel")
    with right:
        # IMPORTANT: don't assign to a local variable; Streamlit writes to session_state
        st.radio(
            "Units",
            options=["Auto", "kg", "lb"],
            horizontal=True,
            label_visibility="collapsed",
            key="unit_mode",
        )

    # ALWAYS read the current value from session_state (fixes "stays kg" bug)
    unit_mode = st.session_state.get("unit_mode", "Auto")

    # SimBrief units (from parser)
    sb_weight_unit = (info.get("weight_unit") or "kg").lower()
    sb_fuel_unit = (info.get("fuel_unit") or sb_weight_unit).lower()

    # Display units based on control
    if unit_mode == "Auto":
        disp_weight_unit = sb_weight_unit
        disp_fuel_unit = sb_fuel_unit
    else:
        disp_weight_unit = unit_mode
        disp_fuel_unit = unit_mode

    pax = info.get("pax")  # count
    cargo_raw = _to_float(info.get("cargo"))
    block_fuel_raw = _to_float(info.get("block_fuel"))
    zfw_raw = _to_float(info.get("zfw"))
    tow_raw = _to_float(info.get("tow"))

    # Convert values
    cargo = _convert_mass(cargo_raw, sb_weight_unit, disp_weight_unit)
    zfw = _convert_mass(zfw_raw, sb_weight_unit, disp_weight_unit)
    tow = _convert_mass(tow_raw, sb_weight_unit, disp_weight_unit)
    block_fuel = _convert_mass(block_fuel_raw, sb_fuel_unit, disp_fuel_unit)

    r1, r2, r3, r4, r5 = st.columns(5)
    with r1:
        card("Passengers", f"{pax}" if pax is not None else "N/A", "")
    with r2:
        card("Cargo", _fmt_mass(cargo, disp_weight_unit), "")
    with r3:
        card("Block Fuel", _fmt_mass(block_fuel, disp_fuel_unit), "")
    with r4:
        card("ZFW", _fmt_mass(zfw, disp_weight_unit), "")
    with r5:
        card("TOW", _fmt_mass(tow, disp_weight_unit), "")

    # -------------------------
    # METARs
    # -------------------------
    if orig_metar or dest_metar:
        st.subheader("Weather (METAR)")
        m1, m2 = st.columns(2)

        with m1:
            st.markdown(
                f'<div class="if-chip if-chip-blue">Departure METAR ({_esc(origin or "DEP")})</div>',
                unsafe_allow_html=True,
            )
            decoded = decode_metar(orig_metar)
            st.markdown(
                f"""
                <div class="if-card">
                  <div class="if-card-title">Decoded</div>
                  <div class="if-body">{_esc(decoded)}</div>
                  <div class="if-card-title" style="margin-top:0.6rem;">Raw</div>
                  <div class="if-pre">{_esc(orig_metar or "N/A")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m2:
            st.markdown(
                f'<div class="if-chip if-chip-orange">Arrival METAR ({_esc(destination or "ARR")})</div>',
                unsafe_allow_html=True,
            )
            decoded = decode_metar(dest_metar)
            st.markdown(
                f"""
                <div class="if-card">
                  <div class="if-card-title">Decoded</div>
                  <div class="if-body">{_esc(decoded)}</div>
                  <div class="if-card-title" style="margin-top:0.6rem;">Raw</div>
                  <div class="if-pre">{_esc(dest_metar or "N/A")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # -------------------------
    # Takeoff settings (N1)
    # -------------------------
    if aircraft == "A220-300":
        st.warning("A220-300: SimBrief does not provide takeoff TLR data in JSON. N1 calculations disabled.")
        return

    try:
        n1_result = compute_takeoff_from_info(info, aircraft)
    except Exception as e:
        st.error(f"Error computing N1: {e}")
        return

    st.subheader("Takeoff Settings")

    n1_val = n1_result.get("N1_percent")
    slider_val = n1_result.get("IF_slider_percent")
    flaps = n1_result.get("flaps") or info.get("flaps")

    c1, c2, c3 = st.columns(3)
    with c1:
        card("N1 (Operational)", f"{n1_val:.2f} %" if n1_val is not None else "N/A", "Target takeoff N1")
    with c2:
        card("IF Power Slider", f"{slider_val:.1f} %" if slider_val is not None else "N/A", "Set in Infinite Flight")
    with c3:
        card("Flap Setting", f"{flaps}" if flaps else "N/A", "Takeoff config")

    st.subheader("Thrust Profile & V-Speeds")

    mode_raw = n1_result.get("thrust_mode_raw") or info.get("mode_raw")
    mode_norm = n1_result.get("thrust_mode_normalized") or info.get("mode_normalized")
    thrust_profile = mode_raw or mode_norm

    speeds = n1_result.get("speeds") or info.get("speeds") or {}
    v1 = speeds.get("V1")
    vr = speeds.get("VR")
    v2 = speeds.get("V2")

    t1, t2, t3, t4 = st.columns(4)
    with t1:
        card("Thrust Mode", thrust_profile or "N/A", "TO / D-TO / FLEX")
    with t2:
        card("V1", f"{v1} kt" if v1 is not None else "N/A", "Decision")
    with t3:
        card("VR", f"{vr} kt" if vr is not None else "N/A", "Rotate")
    with t4:
        card("V2", f"{v2} kt" if v2 is not None else "N/A", "Climb")


def main():
    st.title("SimBrief → Infinite Flight Takeoff Helper")
    st.write(
        "Enter your SimBrief username to fetch your latest OFP (JSON) and compute takeoff settings."
        " Supported aircraft: B737 MAX 8, B777-200ER, A380-800."
    )

    username = st.text_input("SimBrief Username", value=st.session_state["username"], max_chars=64)
    st.session_state["username"] = username

    col_a, col_b = st.columns([0.75, 0.25])
    with col_a:
        fetch_clicked = st.button("Fetch from SimBrief", use_container_width=True)
    with col_b:
        clear_clicked = st.button("Clear", use_container_width=True)

    if clear_clicked:
        st.session_state["ofp"] = None
        st.session_state["info"] = None
        st.session_state["aircraft"] = None

    if fetch_clicked and username.strip():
        with st.spinner("Fetching OFP from SimBrief..."):
            try:
                ofp = fetch_simbrief_ofp_json(username.strip())
            except Exception as e:
                st.error(f"Error fetching SimBrief OFP: {e}")
                return

        aircraft = detect_aircraft_from_json(ofp) or "Unknown"

        overview = parse_ofp_overview_from_json(ofp)

        tk: Dict[str, Any] = {}
        try:
            tk = parse_takeoff_from_json(ofp)
        except SimBriefTLRError:
            tk = {}

        info: Dict[str, Any] = {}
        info.update(overview)
        info.update(tk)

        # Cache so unit switching doesn't refetch/reset
        st.session_state["ofp"] = ofp
        st.session_state["aircraft"] = aircraft
        st.session_state["info"] = info

    # Always render if cached
    if st.session_state["info"] is not None:
        st.info(f"Detected aircraft: **{st.session_state['aircraft']}**")
        run_takeoff_pipeline(st.session_state["info"], st.session_state["aircraft"])


if __name__ == "__main__":
    main()
