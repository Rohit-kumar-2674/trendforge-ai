def classify(
    *,
    growth: float,
    acceleration: float,
    persistence: float,
    current: float,
    baseline: float,
    historic_peak: float,
    n: int,
) -> str:
    if n < 21:
        return "Emerging"
    if current < max(1e-9, historic_peak * 0.05):
        return "Dormant"
    if growth > 0.1 and current < historic_peak * 0.65 and acceleration > 0:
        return "Resurgent"
    if growth < -0.08:
        return "Declining"
    if growth < -0.015:
        return "Cooling"
    if current > baseline * 1.7 and growth > 0.15 and persistence > 0.55:
        return "Breakout"
    if growth > 0.04 and acceleration > 0:
        return "Accelerating"
    if growth > 0.025:
        return "Early Growth"
    if acceleration < 0 and current > historic_peak * 0.9:
        return "Peaking"
    if current > baseline * 1.3:
        return "Mainstream"
    return "Mature"
