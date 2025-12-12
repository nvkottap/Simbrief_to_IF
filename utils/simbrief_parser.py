# utils/simbrief_parser.py

from __future__ import annotations
from typing import Any, Dict, Optional
import re


class SimBriefTLRError(Exception):
    """Raised when TLR (takeoff) data is missing or unusable."""


# =============================================================================
# AIRCRAFT DETECTION
# =============================================================================

def _normalize_ac_name(name: str) -> str:
    name = name.upper().strip()
    if "737" in name and "MAX" in name:
        return "B737 MAX 8"
    if "B38M" in name:
        return "B737 MAX 8"
    if "777-200" in name or "B772" in name:
        return "B777-200ER"
    if "777-300" in name or "B77W" in name:
        return "B777-300ER"
    if "A220-300" in name or "A223" in name or "BCS3" in name:
        return "A220-300"
    if "A380-800" in name or "A388" in name:
        return "A380-800"
    return ""


def detect_aircraft_from_json(ofp: Dict[str, Any]) -> Optional[str]:
    ac = ofp.get("aircraft", {}) or {}
    candidates = [
        ac.get("name"),
        ac.get("base_type"),
        ac.get("list_type"),
        ac.get("icao_code"),
        ac.get("icaocode"),
    ]
    for c in candidates:
        if not c:
            continue
        norm = _normalize_ac_name(str(c))
        if norm:
            return norm
    return None


def detect_aircraft_from_text(text: str) -> Optional[str]:
    t = text.upper()
    if "B737 MAX 8" in t or "737 MAX 8" in t or "B38M" in t:
        return "B737 MAX 8"
    if "B777-200ER" in t or "B772" in t:
        return "B777-200ER"
    if "B777-300ER" in t or "B77W" in t:
        return "B777-300ER"
    if "A380-800" in t or "A388" in t:
        return "A380-800"
    if "A220-300" in t or "A223" in t or "BCS3" in t:
        return "A220-300"
    return None


# =============================================================================
# FLEX DETECTOR
# =============================================================================

def is_flex_active(oat_C: Optional[float],
                   sel_temp_C: Optional[float],
                   mode_raw: Optional[str]) -> bool:
    if mode_raw and "FLEX" in str(mode_raw).upper():
        return True
    if oat_C is not None and sel_temp_C is not None:
        if sel_temp_C > oat_C + 0.9:
            return True
    return False


# =============================================================================
# HELPERS
# =============================================================================

def _normalize_mode(thrust_setting: str) -> str:
    if not thrust_setting:
        return "MAX"
    t = thrust_setting.upper()
    if "FLEX" in t:
        return "FLEX"
    if "TO2" in t or "D-TO2" in t:
        return "TO2"
    if "TO1" in t or "D-TO1" in t:
        return "TO1"
    return "MAX"


def _safe_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except Exception:
        return None


def _normalize_unit(u: Any) -> str:
    """
    Normalize SimBrief unit strings to either 'kg' or 'lb' where possible.
    """
    if not u:
        return ""
    s = str(u).strip().lower()
    s = s.replace("kgs", "kg").replace("kilograms", "kg").replace("kilogram", "kg")
    s = s.replace("lbs", "lb").replace("pounds", "lb").replace("pound", "lb")
    if s in {"kg", "lb"}:
        return s
    return s


# =============================================================================
# TLR PARSER (JSON)
# =============================================================================

def parse_takeoff_from_json(ofp: Dict[str, Any]) -> Dict[str, Any]:
    tlr = ofp.get("tlr")
    if not tlr or "takeoff" not in tlr:
        raise SimBriefTLRError("No TLR takeoff data in JSON.")

    takeoff = tlr["takeoff"]
    conds = takeoff.get("conditions", {}) or {}
    runways = takeoff.get("runway", []) or []

    if not runways:
        raise SimBriefTLRError("No runway entries in TLR.")

    planned_rwy = conds.get("planned_runway")
    rwy = None
    for r in runways:
        if planned_rwy and str(r.get("identifier")) == str(planned_rwy):
            rwy = r
            break
    if rwy is None:
        rwy = runways[0]  # fallback

    airport = conds.get("airport_icao") or conds.get("airport")
    runway = rwy.get("identifier")

    oat_C = _safe_float(conds.get("temperature"))
    qnh = _safe_float(conds.get("altimeter"))
    elev_ft = _safe_float(rwy.get("elevation"))

    # pressure altitude approximation (same approach you used earlier)
    pressure_alt_ft = None
    if elev_ft is not None and qnh is not None:
        pressure_alt_ft = elev_ft + 27.0 * (29.92 - qnh)
    else:
        pressure_alt_ft = elev_ft

    thrust_setting = rwy.get("thrust_setting")
    mode_normalized = _normalize_mode(thrust_setting or "")

    bleeds = rwy.get("bleed_setting") or "AUTO"
    packs_for_calc = (str(bleeds).upper() != "OFF")

    aice_raw = rwy.get("anti_ice_setting") or "OFF"
    anti_ice_for_calc = (str(aice_raw).upper() not in {"OFF", ""})

    sel_temp_C = _safe_float(rwy.get("flex_temperature"))
    if sel_temp_C is None:
        sel_temp_C = _safe_float(rwy.get("max_temperature"))

    flaps = rwy.get("flap_setting")

    def _safe_int(x):
        try:
            return int(round(float(x)))
        except Exception:
            return None

    speeds = {
        "V1": _safe_int(rwy.get("speeds_v1")),
        "VR": _safe_int(rwy.get("speeds_vr")),
        "V2": _safe_int(rwy.get("speeds_v2")),
    }

    return {
        "airport": airport,
        "runway": runway,
        "oat_C": oat_C,
        "elevation_ft": elev_ft,
        "pressure_alt_ft": pressure_alt_ft,
        "qnh_inhg": qnh,

        "mode_raw": thrust_setting,
        "mode_normalized": mode_normalized,
        "bleeds": bleeds,
        "packs_for_calc": packs_for_calc,
        "aice_raw": aice_raw,
        "anti_ice_for_calc": anti_ice_for_calc,
        "sel_temp_C": sel_temp_C,

        "flaps": flaps,
        "speeds": speeds,
    }


# =============================================================================
# OFP OVERVIEW PARSER
# =============================================================================

def parse_ofp_overview_from_json(ofp: Dict[str, Any]) -> Dict[str, Any]:
    general = ofp.get("general", {}) or {}
    weather = ofp.get("weather", {}) or {}
    weights = ofp.get("weights", {}) or {}
    fuel = ofp.get("fuel", {}) or {}
    tlr = ofp.get("tlr", {}) or {}
    units = ofp.get("units", {}) or {}

    # --- Units (NEW) ---
    # Most reliable: ofp["units"]["weight"] / ["fuel"]
    weight_unit = _normalize_unit(units.get("weight")) or _normalize_unit(weights.get("unit")) or _normalize_unit(general.get("units")) or "kg"
    fuel_unit = _normalize_unit(units.get("fuel")) or weight_unit

    origin = general.get("orig_icao") or general.get("orig") or general.get("orig_code")
    dest = general.get("dest_icao") or general.get("dest") or general.get("dest_code")

    origin_name = general.get("orig_name")
    dest_name = general.get("dest_name")

    takeoff = tlr.get("takeoff", {}) or {}
    landing = tlr.get("landing", {}) or {}

    if not origin:
        tconds = takeoff.get("conditions", {}) or {}
        origin = tconds.get("airport_icao") or origin

    if not dest:
        lconds = landing.get("conditions", {}) or {}
        dest = lconds.get("airport_icao") or dest

    # Departure runway info (TLR takeoff)
    dep_runway_id = None
    dep_runway_length_ft = None
    dep_elev_ft = None

    if takeoff:
        tconds = takeoff.get("conditions", {}) or {}
        planned_dep = tconds.get("planned_runway")
        trwys = takeoff.get("runway", []) or []

        sel_rwy = None
        for r in trwys:
            if planned_dep and str(r.get("identifier")) == str(planned_dep):
                sel_rwy = r
                break
        if sel_rwy is None and trwys:
            sel_rwy = trwys[0]

        if sel_rwy:
            dep_runway_id = sel_rwy.get("identifier")
            dep_runway_length_ft = _safe_float(sel_rwy.get("length_tora") or sel_rwy.get("length"))
            dep_elev_ft = _safe_float(sel_rwy.get("elevation"))

    # Arrival runway info (TLR landing)
    arr_runway_id = None
    arr_runway_length_ft = None
    arr_elev_ft = None

    if landing:
        lconds = landing.get("conditions", {}) or {}
        planned_arr = lconds.get("planned_runway")
        lrwys = landing.get("runway", []) or []

        sel_l_rwy = None
        for r in lrwys:
            if planned_arr and str(r.get("identifier")) == str(planned_arr):
                sel_l_rwy = r
                break
        if sel_l_rwy is None and lrwys:
            sel_l_rwy = lrwys[0]

        if sel_l_rwy:
            arr_runway_id = sel_l_rwy.get("identifier")
            arr_runway_length_ft = _safe_float(sel_l_rwy.get("length_lda") or sel_l_rwy.get("length"))
            arr_elev_ft = _safe_float(sel_l_rwy.get("elevation"))

    route = general.get("route") or general.get("navlog_route") or general.get("plan_rte")

    # --- Fuel / weights / payload ---
    block_fuel = (
        fuel.get("plan_ramp")
        or fuel.get("block")
        or fuel.get("block_fuel")
        or fuel.get("total_fuel")
    )

    zfw = (
        weights.get("zfw")
        or weights.get("planned_zfw")
        or weights.get("est_zfw")
    )

    tow = (
        weights.get("tow")
        or weights.get("planned_tow")
        or weights.get("est_tow")
    )

    pax = (
        weights.get("pax_count_actual")
        or weights.get("pax")
        or weights.get("passengers")
    )

    cargo = (
        weights.get("cargo")
        or weights.get("cargo_weight")
        or general.get("cargo")
    )

    orig_metar = weather.get("orig_metar") or weather.get("orig_metar_text")
    dest_metar = weather.get("dest_metar") or weather.get("dest_metar_text")

    return {
        "origin": origin,
        "origin_name": origin_name,
        "destination": dest,
        "destination_name": dest_name,

        "dep_runway": dep_runway_id,
        "dep_runway_length_ft": dep_runway_length_ft,
        "dep_elev_ft": dep_elev_ft,

        "arr_runway": arr_runway_id,
        "arr_runway_length_ft": arr_runway_length_ft,
        "arr_elev_ft": arr_elev_ft,

        "route_string": route,

        # payload/fuel summary
        "block_fuel": block_fuel,
        "zfw": zfw,
        "tow": tow,
        "pax": pax,
        "cargo": cargo,

        # units (NEW)
        "weight_unit": weight_unit,
        "fuel_unit": fuel_unit,

        # metars
        "orig_metar": orig_metar,
        "dest_metar": dest_metar,
    }
