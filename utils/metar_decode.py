# utils/metar_decode.py

import re
from typing import Optional


def decode_metar(metar_text: Optional[str]) -> str:
    """
    Lightweight, tolerant METAR decoder tuned for SimBrief-style METAR strings.

    Handles:
      - Station
      - Wind (dddssKT, gusts, VRB)
      - Visibility (SM or meters)
      - Clouds (FEW/SCT/BKN/OVC xxx)
      - Temperature/dewpoint (T/Td with M prefix for minus)
      - Altimeter (A2992 or Q1013)
      - Basic weather codes (+RA, BR, FG, etc.)

    We intentionally do NOT decode/show the observation time.

    If we can't parse anything meaningful, we fall back to the raw METAR.
    """
    if not metar_text:
        return "No METAR available"

    text = metar_text.strip()
    tokens = text.split()
    parts = []

    # --- Station (first 4-letter token is usually ICAO) ---
    if tokens and re.match(r"^[A-Z]{4}$", tokens[0]):
        station = tokens[0]
        parts.append(f"Airport: {station}")

    # NOTE: We intentionally do NOT decode / show time anymore.

    # --- Wind: dddssKT or VRBssKT with optional gusts GgggKT ---
    for tok in tokens:
        m = re.match(
            r"^(?P<dir>\d{3}|VRB)(?P<spd>\d{2,3})(G(?P<gst>\d{2,3}))?KT$",
            tok
        )
        if m:
            d = m.group("dir")
            s = m.group("spd")
            g = m.group("gst")
            if d == "VRB":
                base = "Variable"
            else:
                base = f"{d}°"
            if g:
                parts.append(f"Wind: {base} at {s} kt gusting {g} kt")
            else:
                parts.append(f"Wind: {base} at {s} kt")
            break

    # --- Visibility: ##SM, #/#SM, or 4-digit meters ---
    for tok in tokens:
        # e.g. 10SM or 3SM
        m = re.match(r"^(\d+)(SM)$", tok)
        if m:
            parts.append(f"Visibility: {m.group(1)} sm")
            break

        # e.g. 3/4SM
        m = re.match(r"^(\d+/\d+)(SM)$", tok)
        if m:
            parts.append(f"Visibility: {m.group(1)} sm")
            break

        # e.g. 9999 / 6000 / 0800 style meters
        m = re.match(r"^(\d{4})$", tok)
        if m:
            val = int(m.group(1))
            parts.append(f"Visibility: {val} m")
            break

    # --- Clouds: FEW/SCT/BKN/OVC with 3-digit height ---
    clouds = []
    for tok in tokens:
        m = re.match(r"^(FEW|SCT|BKN|OVC)(\d{3})", tok)
        if m:
            amt = m.group(1)
            height_hundreds = int(m.group(2))
            height_ft = height_hundreds * 100
            label_map = {
                "FEW": "Few",
                "SCT": "Scattered",
                "BKN": "Broken",
                "OVC": "Overcast",
            }
            label = label_map.get(amt, amt)
            clouds.append(f"{label} at {height_ft} ft")
    if clouds:
        parts.append("Clouds: " + ", ".join(clouds))

    # --- Temperature / Dewpoint: T/Td with optional M prefix (minus) ---
    for tok in tokens:
        m = re.match(r"^(M?\d{1,2})/(M?\d{1,2})$", tok)
        if m:
            def _parse_temp(s: str) -> int:
                if s.startswith("M"):
                    return -int(s[1:])
                return int(s)

            t = _parse_temp(m.group(1))
            d = _parse_temp(m.group(2))
            parts.append(f"Temp/Dew: {t}°C / {d}°C")
            break

    # --- Altimeter: A2992 (inHg) or Q1013 (hPa) ---
    for tok in tokens:
        # Inches of mercury
        m = re.match(r"^A(\d{4})$", tok)
        if m:
            v = int(m.group(1))
            parts.append(f"Altimeter: {v / 100:.2f} inHg")
            break

        # hPa / millibars
        m = re.match(r"^Q(\d{4})$", tok)
        if m:
            v = int(m.group(1))
            parts.append(f"Altimeter: {v} hPa")
            break

    # --- Weather codes: +RA, -RA, BR, FG, TS, etc. ---
    wx_codes = []
    for tok in tokens:
        if re.match(r"^(\+|\-)?(RA|SN|TS|DZ|FG|BR|HZ|FU|SG|PL|GR|GS|IC|SA|DU|SQ|PO|FC|SS|DS)+$", tok):
            wx_codes.append(tok)
    if wx_codes:
        parts.append("Weather: " + ", ".join(wx_codes))

    if not parts:
        return f"Decoded METAR unavailable\nRaw: {metar_text}"

    return "\n".join(parts)