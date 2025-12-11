# utils/simbrief_api_json.py

import requests
from typing import Any, Dict

SIMBRIEF_JSON_URL = "https://www.simbrief.com/api/xml.fetcher.php"


class SimBriefError(Exception):
    pass


def fetch_latest_ofp_json(username: str) -> Dict[str, Any]:
    """
    Fetch latest SimBrief OFP as JSON for a given username.
    """
    username = username.strip()
    if not username:
        raise SimBriefError("Empty SimBrief username.")

    params = {"username": username, "json": 1}

    try:
        resp = requests.get(SIMBRIEF_JSON_URL, params=params, timeout=10)
    except requests.RequestException as e:
        raise SimBriefError(f"Error contacting SimBrief: {e}") from e

    if resp.status_code != 200:
        raise SimBriefError(f"SimBrief returned HTTP {resp.status_code}.")

    try:
        data = resp.json()
    except ValueError as e:
        raise SimBriefError("SimBrief did not return valid JSON.") from e

    # SimBrief wraps the real payload under "ofp"
    ofp = data.get("ofp") or data
    return ofp