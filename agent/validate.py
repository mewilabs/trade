"""Pick validation, shared by the pipeline and the Claude Code hook."""


def validate_pick(p: dict, min_rr: float = 1.5) -> list:
    errs, sym = [], p.get("symbol", "?")
    try:
        e, s, t = float(p["entry"]), float(p["stop_loss"]), float(p["target1"])
    except (KeyError, TypeError, ValueError):
        return [f"{sym}: missing entry/stop/target"]
    if e == s:
        return [f"{sym}: stop equals entry"]
    d = p.get("direction")
    if d == "Buy" and not (s < e < t):
        errs.append(f"{sym}: Buy needs stop < entry < target")
    elif d == "Sell" and not (t < e < s):
        errs.append(f"{sym}: Sell needs target < entry < stop")
    elif d not in ("Buy", "Sell"):
        errs.append(f"{sym}: direction must be Buy or Sell")
    rr = abs(t - e) / abs(e - s)
    if rr < min_rr:
        errs.append(f"{sym}: R:R {rr:.2f} below {min_rr}")
    return errs
