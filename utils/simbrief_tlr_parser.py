# utils/simbrief_tlr_parser.py

from typing import Any, Dict, Optional


class SimBriefTLRError(Exception):
    pass


def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in (None, "", {}, []):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def pressure_alt_from_qnh(elev_ft: float, qnh_inhg: float) -> float:
    """
    Very simple approximation:
      1 inHg ≈ 1000 ft
      PA = field_elev + (29.92 - QNH) * 1000
    """
    return elev_ft + (29.92 - qnh_inhg) * 1000.0


def parse_tlr_takeoff(ofp_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts the key takeoff data from SimBrief JSON (tlr.takeoff).

    Returns a dict with:
        airport_icao, runway_id, oat_C, qnh_inhg,
        field_elev_ft, pressure_alt_ft,
        planned_tow_kg,
        flaps, thrust_setting, bleed_setting, anti_ice_setting,
        sel_temp_C,
        v1, vr, v2
    """
    tlr = ofp_json.get("tlr")
    if not tlr or "takeoff" not in tlr:
        raise SimBriefTLRError("No TLR takeoff section found in SimBrief JSON.")

    takeoff = tlr["takeoff"]
    cond = takeoff.get("conditions") or {}
    runways = takeoff.get("runway") or []

    if not runways:
        raise SimBriefTLRError("No TLR takeoff runway entries found.")

    airport_icao = cond.get("airport_icao", "").upper()
    planned_rwy = str(cond.get("planned_runway", "")).upper()

    # Choose the runway entry:
    selected = None
    if planned_rwy:
        for r in runways:
            if str(r.get("identifier", "")).upper() == planned_rwy:
                selected = r
                break
    if selected is None:
        # fallback: just first runway
        selected = runways[0]

    # Basic conditions
    oat_C = _to_float(cond.get("temperature"), 15.0)
    qnh_inhg = _to_float(cond.get("altimeter"), 29.92)
    planned_weight = _to_float(cond.get("planned_weight"))

    rwy_id = str(selected.get("identifier", ""))
    field_elev_ft = _to_float(selected.get("elevation"), 0.0)
    pressure_alt_ft = pressure_alt_from_qnh(field_elev_ft or 0.0, qnh_inhg or 29.92)

    flaps = str(selected.get("flap_setting", "")).strip()
    thrust_setting = str(selected.get("thrust_setting", "")).strip()   # e.g. "D-TO2", "TO", "FLEX"
    bleed_setting = str(selected.get("bleed_setting", "")).strip().upper()  # "ON"/"OFF"
    anti_ice_setting = str(selected.get("anti_ice_setting", "")).strip().upper()

    sel_temp_C = _to_float(selected.get("flex_temperature"))

    v1 = _to_float(selected.get("speeds_v1"))
    vr = _to_float(selected.get("speeds_vr"))
    v2 = _to_float(selected.get("speeds_v2"))

    return {
        "airport_icao": airport_icao,
        "runway_id": rwy_id,
        "oat_C": oat_C,
        "qnh_inhg": qnh_inhg,
        "field_elev_ft": field_elev_ft,
        "pressure_alt_ft": pressure_alt_ft,
        "planned_tow_kg": planned_weight,
        "flaps": flaps,
        "thrust_setting": thrust_setting,
        "bleed_setting": bleed_setting,
        "anti_ice_setting": anti_ice_setting,
        "sel_temp_C": sel_temp_C,
        "v1": v1,
        "vr": vr,
        "v2": v2,
    }