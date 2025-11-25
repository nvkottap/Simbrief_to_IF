def n1_to_slider(n1_percent: float) -> float:
    """
    IF mapping:
       slider 0  → 20% N1
       slider 100 → 101% N1
    """
    slider = (n1_percent - 20.0) / 81.0 * 100.0
    return min(max(slider, 0.0), 100.0)

def slider_to_n1(slider_percent: float) -> float:
    """
    Inverse of the mapping above.
    """
    return 20.0 + (slider_percent / 100.0) * 81.0
