import html
from typing import Any, Dict

import requests
import streamlit as st

from utils.simbrief_parser import (
    detect_aircraft_from_json,
    parse_takeoff_from_json,
    parse_ofp_overview_from_json,
)
from utils.n1_dispatcher import compute_takeoff_from_info
from utils.metar_decode import decode_metar


# ----------------------------------------------------------------------
# Page config + CSS theme
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="IF Takeoff Helper",
    page_icon="✈️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .if-card {
        background-color: #0f172a;
        border-radius: 0.75rem;
        padding: 0.75rem 1rem;
        border: 1px solid #1f2937;
        margin-bottom: 0.75rem;
    }
    .if-card-title {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #9ca3af;
        margin-bottom: 0.15rem;
    }
    .if-card-value {
        font-size: 1.4rem;
        font-weight: 600;
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
        margin-bottom: 0.4rem;
    }
    .if-chip-blue { background-color: #1d4ed8; color: #eff6ff; }
    .if-chip-orange { background-color: #c2410c; color: #fff7ed; }
    .if-chip-green { background-color: #065f46; color: #ecfdf5; }
    .if-small {
        font-size: 0.9rem;
        color: #e5e7eb;
        line-height: 1.35;
        white-space: pre-line;
    }
    .if-pre {
        background: #0b1220;
        border: 1px solid #1f2937;
        border-radius: 0.6rem;
        padding: 0.75rem 0.85rem;
        color: #e5e7eb;
        overflow-x: auto;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.9rem;
        margin-top: 0.35rem;
        margin-bottom: 0.25rem;
        white-space: pre-wrap;
        word-break: break-word;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ----------------------------------------------------------------------
# Helper: fetch SimBrief OFP JSON for a username
# ----------------------------------------------------------------------
def fetch_simbrief_ofp_json(username: str) -> Dict[str, Any]:
    """
    Fetch SimBrief OFP JSON via the public API (latest OFP for username).
    """
    base_url = "https://www.simbrief.com/api/xml.fetcher.php"  # correct endpoint
    params = {"username": username, "json": "v2"}  # v2 tends to be more stable

    resp = requests.get(base_url, params=params, timeout=20)

    if resp.status_code in (400, 404):
        raise RuntimeError(
            f"SimBrief fetch failed (HTTP {resp.status_code}). "
            "Double-check the SimBrief username and ensure a recent OFP was generated."
        )

    resp.raise_for_status()

    try:
        ofp = resp.json()
    except Exception:
        raise RuntimeError(f"SimBrief did not return JSON. Response was:\n{resp.text[:800]}")

    if not isinstance(ofp, dict):
        raise ValueError("SimBrief JSON response is not a dict")

    return ofp


def _escape(s: Any) -> str:
    return html.escape("" if s is None else str(s))


# ----------------------------------------------------------------------
# Shared pipeline: take parsed info + aircraft → compute N1 → render UI
# ----------------------------------------------------------------------
def run_takeoff_pipeline_from_info(info: Dict[str, Any], aircraft: str):
    """
    Shared display pipeline: takes parsed SimBrief info + aircraft,
    calls N1 dispatcher, and renders a text-based UI with consistent styling.
    """

    # A220-300: currently no TLR data in JSON → show overview only
    n1_result = None
    if aircraft == "A220-300":
        st.warning(
            "A220-300 detected.\n\n"
            "SimBrief does not currently provide the TLR takeoff section we need via JSON "
            "for this aircraft, so N1 calculations are not available yet.\n\n"
            "Flight overview and METARs are still shown."
        )
    else:
        if aircraft not in {"B737 MAX 8", "B777-200ER", "B777-300ER", "A380-800"}:
            st.warning(
                f"Aircraft '{aircraft}' is not yet supported for automatic N1.\n\n"
                "Support for additional types will be added over time."
            )
            return

        try:
            n1_result = compute_takeoff_from_info(info, aircraft)
        except Exception as e:
            st.error(f"Error computing N1: {e}")
            return

    result: Dict[str, Any] = {}
    if n1_result is not None:
        result.update(n1_result)

    # ------------------------------------------------------------------
    # 1) Flight Overview
    # ------------------------------------------------------------------
    st.subheader("Flight Overview")

    origin = info.get("origin") or result.get("airport")
    origin_name = info.get("origin_name")
    destination = info.get("destination")
    destination_name = info.get("destination_name")

    dep_runway = info.get("dep_runway") or info.get("runway")
    dep_len = info.get("dep_runway_length_ft")
    dep_elev = info.get("dep_elev_ft") or info.get("elevation_ft")

    arr_runway = info.get("arr_runway")
    arr_len = info.get("arr_runway_length_ft")
    arr_elev = info.get("arr_elev_ft")

    route_str = info.get("route_string")

    orig_metar = info.get("orig_metar")
    dest_metar = info.get("dest_metar")

    # Departure vs Arrival cards (content INSIDE the card HTML)
    c_dep, c_arr = st.columns(2)

    with c_dep:
        st.markdown('<div class="if-chip if-chip-blue">Departure</div>', unsafe_allow_html=True)

        dep_title = origin or "N/A"
        if origin and origin_name:
            dep_title = f"{origin} – {origin_name}"

        runway_line = f"<div><b>Runway:</b> {_escape(dep_runway)}</div>" if dep_runway else ""
        details = []
        if dep_elev is not None:
            details.append(f"Elevation: {dep_elev:.0f} ft")
        if dep_len is not None:
            details.append(f"Length: {dep_len:.0f} ft")
        details_line = f"<div>{_escape(' · '.join(details))}</div>" if details else ""

        card_html = f"""
        <div class="if-card">
          <div style="font-size:1.35rem; font-weight:700; color:#f9fafb; margin-bottom:0.25rem;">
            {_escape(dep_title)}
          </div>
          <div style="color:#e5e7eb; font-size:1rem; line-height:1.5;">
            {runway_line}
            {details_line}
          </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

    with c_arr:
        st.markdown('<div class="if-chip if-chip-orange">Arrival</div>', unsafe_allow_html=True)

        arr_title = destination or "N/A"
        if destination and destination_name:
            arr_title = f"{destination} – {destination_name}"

        runway_line = f"<div><b>Runway:</b> {_escape(arr_runway)}</div>" if arr_runway else ""
        details = []
        if arr_elev is not None:
            details.append(f"Elevation: {arr_elev:.0f} ft")
        if arr_len is not None:
            details.append(f"Length: {arr_len:.0f} ft")
        details_line = f"<div>{_escape(' · '.join(details))}</div>" if details else ""

        card_html = f"""
        <div class="if-card">
          <div style="font-size:1.35rem; font-weight:700; color:#f9fafb; margin-bottom:0.25rem;">
            {_escape(arr_title)}
          </div>
          <div style="color:#e5e7eb; font-size:1rem; line-height:1.5;">
            {runway_line}
            {details_line}
          </div>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)

    # Aircraft card (below the two columns)
    st.markdown(
        f"""
        <div class="if-card">
          <div class="if-card-title">Aircraft</div>
          <div class="if-card-value">{_escape(aircraft)}</div>
          <div class="if-card-sub">Based on SimBrief OFP and TLR data</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Route string
    if route_str:
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">Route</div>
              <div class="if-pre">{_escape(route_str)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------------
    # 2) METARs
    # ------------------------------------------------------------------
    if orig_metar or dest_metar:
        st.subheader("Weather (METAR)")

        m1, m2 = st.columns(2)

        with m1:
            st.markdown(
                f'<div class="if-chip if-chip-blue">Departure METAR ({_escape(origin or "DEP")})</div>',
                unsafe_allow_html=True,
            )
            decoded = decode_metar(orig_metar)
            st.markdown(
                f"""
                <div class="if-card">
                  <div class="if-small">{_escape(decoded)}</div>
                  <div class="if-card-title" style="margin-top:0.6rem;">Raw METAR</div>
                  <div class="if-pre">{_escape(orig_metar or "N/A")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with m2:
            st.markdown(
                f'<div class="if-chip if-chip-orange">Arrival METAR ({_escape(destination or "ARR")})</div>',
                unsafe_allow_html=True,
            )
            decoded = decode_metar(dest_metar)
            st.markdown(
                f"""
                <div class="if-card">
                  <div class="if-small">{_escape(decoded)}</div>
                  <div class="if-card-title" style="margin-top:0.6rem;">Raw METAR</div>
                  <div class="if-pre">{_escape(dest_metar or "N/A")}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # If this aircraft has no N1 result (e.g., A220), stop here.
    if n1_result is None:
        return

    # ------------------------------------------------------------------
    # 3) Takeoff Settings (N1, IF slider, flaps)
    # ------------------------------------------------------------------
    st.subheader("Takeoff Settings")

    n1_val = result.get("N1_percent")
    slider_val = result.get("IF_slider_percent")
    flaps = result.get("flaps") or info.get("flaps")

    c1, c2, c3 = st.columns(3)

    with c1:
        value = f"{n1_val:.2f} %" if n1_val is not None else "N/A"
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">N1 (Operational)</div>
              <div class="if-card-value">{_escape(value)}</div>
              <div class="if-card-sub">Target engine N1 for takeoff</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        value = f"{slider_val:.1f} %" if slider_val is not None else "N/A"
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">IF Power Slider</div>
              <div class="if-card-value">{_escape(value)}</div>
              <div class="if-card-sub">Set this in Infinite Flight</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c3:
        value = flaps or "N/A"
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">Flap Setting</div>
              <div class="if-card-value">{_escape(value)}</div>
              <div class="if-card-sub">Takeoff configuration</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------------
    # 4) Thrust profile & V-speeds
    # ------------------------------------------------------------------
    st.subheader("Thrust Profile & V-Speeds")

    mode_raw = result.get("thrust_mode_raw") or info.get("mode_raw")
    mode_norm = result.get("thrust_mode_normalized") or info.get("mode_normalized")
    thrust_profile = mode_raw or mode_norm

    speeds = result.get("speeds") or info.get("speeds") or {}
    v1 = speeds.get("V1")
    vr = speeds.get("VR")
    v2 = speeds.get("V2")

    t1, t2, t3, t4 = st.columns(4)

    with t1:
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">Thrust Mode</div>
              <div class="if-card-value">{_escape(thrust_profile or "N/A")}</div>
              <div class="if-card-sub">TO / D-TO / FLEX</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with t2:
        val = f"{v1:.0f} kt" if v1 is not None else "N/A"
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">V1</div>
              <div class="if-card-value">{_escape(val)}</div>
              <div class="if-card-sub">Decision speed</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with t3:
        val = f"{vr:.0f} kt" if vr is not None else "N/A"
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">VR</div>
              <div class="if-card-value">{_escape(val)}</div>
              <div class="if-card-sub">Rotation speed</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with t4:
        val = f"{v2:.0f} kt" if v2 is not None else "N/A"
        st.markdown(
            f"""
            <div class="if-card">
              <div class="if-card-title">V2</div>
              <div class="if-card-value">{_escape(val)}</div>
              <div class="if-card-sub">Takeoff safety speed</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ----------------------------------------------------------------------
# Main Streamlit app
# ----------------------------------------------------------------------
def main():
    st.title("SimBrief → Infinite Flight Takeoff Helper")

    st.write(
        "Enter your **SimBrief username** and I'll pull the latest OFP, "
        "detect the aircraft, and compute operational N1 + IF power level "
        "for supported types."
    )

    username = st.text_input("SimBrief Username", value="", max_chars=64)

    if st.button("Fetch from SimBrief") and username.strip():
        with st.spinner("Fetching OFP from SimBrief..."):
            try:
                ofp = fetch_simbrief_ofp_json(username.strip())
            except Exception as e:
                st.error(f"Error fetching SimBrief OFP: {e}")
                return

        # Detect aircraft
        aircraft = detect_aircraft_from_json(ofp) or "Unknown"
        st.info(f"Detected aircraft from OFP: **{aircraft}**")

        # Parse overview + takeoff data and merge
        try:
            overview = parse_ofp_overview_from_json(ofp)
        except Exception as e:
            st.error(f"Error parsing OFP overview from JSON: {e}")
            return

        try:
            tk = parse_takeoff_from_json(ofp)
        except Exception as e:
            st.error(f"Error parsing TLR takeoff data from JSON: {e}")
            return

        info: Dict[str, Any] = {}
        info.update(overview)
        info.update(tk)

        run_takeoff_pipeline_from_info(info, aircraft)


if __name__ == "__main__":
    main()
