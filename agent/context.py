"""Market context: implied gap from Gift Nifty, global cues, day bias."""
import datetime as dt


def _avg(vals):
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def build_context(today: dt.date, glob: dict, nifty_prev_close: float, gift: float | None, vix_skip: float) -> dict:
    gap = gap_pct = None
    if gift:
        gap = gift - nifty_prev_close
        gap_pct = gap / nifty_prev_close
    score, notes = 0, []

    if gap_pct is None:
        notes.append("Gift Nifty unavailable: bias uses global cues only")
    else:
        score += 2 if gap_pct > 0.003 else 1 if gap_pct > 0.001 else -2 if gap_pct < -0.003 else -1 if gap_pct < -0.001 else 0
    us = _avg([glob.get("spx"), glob.get("nasdaq"), glob.get("dow")])
    asia = _avg([glob.get("nikkei"), glob.get("hangseng")])
    for v in (us, asia):
        if v is not None:
            score += 1 if v > 0.005 else -1 if v < -0.005 else 0
    crude = glob.get("crude")
    if crude is not None and abs(crude) > 0.02:
        score += -1 if crude > 0 else 1  # higher crude is a headwind for India
        notes.append(f"Brent {crude:+.1%}")
    ivix = glob.get("india_vix")
    volatile = ivix is not None and ivix >= vix_skip
    if volatile:
        notes.append(f"India VIX {ivix:.1f} >= {vix_skip:.0f}")

    bias = ("Volatile" if volatile else "Bullish" if score >= 3 else "Mild Bullish" if score >= 1
            else "Neutral" if score == 0 else "Mild Bearish" if score >= -2 else "Bearish")
    return {"date": today.isoformat(), "gift_nifty": gift, "nifty_prev_close": nifty_prev_close,
            "gap": gap, "gap_pct": gap_pct, "spx": glob.get("spx"), "nasdaq": glob.get("nasdaq"),
            "dow": glob.get("dow"), "nikkei": glob.get("nikkei"), "hangseng": glob.get("hangseng"),
            "crude": crude, "usdinr": glob.get("usdinr"), "india_vix": ivix, "us_vix": glob.get("us_vix"),
            "bias": bias, "bias_score": score, "notes": "; ".join(notes)}


def bias_sign(ctx: dict) -> int:
    return 1 if ctx["bias_score"] > 0 else -1 if ctx["bias_score"] < 0 else 0
