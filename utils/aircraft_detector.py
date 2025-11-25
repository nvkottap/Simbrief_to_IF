import re

def detect_aircraft(text: str):
    m = re.search(r"TAKEOFF PERFORMANCE\s*\n(.+)", text)
    if not m:
        return None
    header = m.group(1).upper()

    if "B737" in header and "MAX" in header and "8" in header:
        return "B737 MAX 8"
    if "A320" in header and "NEO" in header:
        return "A320neo"
    if "B787" in header:
        return "B787"

    return None
