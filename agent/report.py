def _fmt(p):
    ins = f" {p['instrument']} {p['strike_expiry']}" if p["instrument"] != "Equity" else ""
    extra = ""
    if p.get("type") == "Short-term" and "momentum_score" in p:
        extra = f" | mom {p.get('momentum_score')} fund {p.get('fund_score')}"
    return (f"{p['id']} | {p['symbol']} {p['direction']}{ins}\n"
            f"   entry {p['entry']} | SL {p['stop_loss']} | T1 {p['target1']} | T2 {p['target2']} | conf {p['confidence']}/5{extra}\n"
            f"   {p['rationale']}")


def build_report(ctx, picks, notes, summary, rec_log, disclaimer) -> str:
    g = f"{ctx['gift_nifty']:.0f} ({ctx['gap_pct']:+.2%})" if ctx.get("gift_nifty") else "n/a"
    lines = [f"PRE-MARKET {ctx['date']} | Bias: {ctx['bias']} | Gift Nifty: {g} | India VIX: {ctx.get('india_vix')}", summary, ""]
    for t in ("Option Scalp", "Intraday", "Short-term"):
        lines.append(f"== {t} ==")
        lines += [_fmt(p) for p in picks if p["type"] == t] or ["   (none today)"]
    if rec_log:
        lines += ["", "== Updated from earlier picks =="] + [f"   {x}" for x in rec_log]
    if notes:
        lines += ["", "== Notes =="] + [f"   {x}" for x in notes]
    return "\n".join(lines + ["", disclaimer])
