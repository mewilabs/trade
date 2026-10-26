"""Deterministic pick construction. All numbers come from here, never from the LLM."""
import datetime as dt
import pandas as pd
from .context import bias_sign
from .indicators import ema, atr
from .validate import validate_pick

INDEX_STEP = {"NIFTY": 50, "BANKNIFTY": 100}


def tick(x: float) -> float:
    return round(round(x / 0.05) * 0.05, 2)


def _bdays_after(d: dt.date, n: int) -> dt.date:
    return (pd.Timestamp(d) + pd.offsets.BDay(n)).date()


def _conf(score: float, aligned: bool) -> int:
    base = int(round(score))
    return max(1, min(5, base + (1 if aligned else 0) - 1))


def _pick(**kw) -> dict:
    kw.setdefault("instrument", "Equity")
    kw.setdefault("strike_expiry", "")
    return kw


def intraday_pick(c: dict, side: int, ctx: dict, today: dt.date, n: int) -> dict:
    risk = 0.6 * c["atr"]
    if side > 0:
        entry = tick(c["prev_high"] * 1.001)
        stop, t1, t2, d = tick(entry - risk), tick(entry + 1.6 * risk), tick(entry + 2.4 * risk), "Buy"
        sig, score = c["long_signals"], c["momentum_score"]
    else:
        entry = tick(c["prev_low"] * 0.999)
        stop, t1, t2, d = tick(entry + risk), tick(entry - 1.6 * risk), tick(entry - 2.4 * risk), "Sell"
        sig, score = c["short_signals"], c["short_score"]
    return _pick(id=f"{today:%Y%m%d}-I{n}", date=today.isoformat(), type="Intraday", symbol=c["symbol"],
                 direction=d, entry=entry, stop_loss=stop, target1=t1, target2=t2,
                 confidence=_conf(score, side == bias_sign(ctx)), valid_until=today.isoformat(),
                 signals=sig, score=score,
                 rationale=f"{'Long' if side > 0 else 'Short'} on break of prior day {'high' if side > 0 else 'low'}; "
                           f"skip if it opens > {0.3 * c['atr']:.1f} beyond entry. Signals: {', '.join(sig)}.")


def short_term_pick(c: dict, ctx: dict, today: dt.date, n: int) -> dict:
    entry = tick(c["close"])
    # tighter of 10d swing low / 2 ATR, floor at 1 ATR
    risk = max(entry - max(c["swing_low10"], entry - 2 * c["atr"]), c["atr"])
    stop = tick(entry - risk)
    fund_bit = f" | Fund: {', '.join(c['fund_signals'])}" if c.get("fund_signals") else ""
    mom_bit = ", ".join(c["long_signals"][:4])
    return _pick(
        id=f"{today:%Y%m%d}-T{n}", date=today.isoformat(), type="Short-term", symbol=c["symbol"],
        direction="Buy", entry=entry, stop_loss=stop,
        target1=tick(entry + 2 * risk), target2=tick(entry + 3 * risk),
        confidence=_conf(c["composite"], bias_sign(ctx) >= 0),
        valid_until=_bdays_after(today, 3).isoformat(),
        signals=c["long_signals"] + c.get("fund_signals", []),
        score=c["composite"],
        momentum_score=c["momentum_score"], fund_score=c["fund_score"],
        rationale=(f"High-momentum quality long (mom {c['momentum_score']}, fund {c['fund_score']}). "
                   f"Entry near prior close, hold up to 10 sessions. {mom_bit}{fund_bit}.")
    )


def scalp_picks(index_hist: dict, ctx: dict, today: dt.date, settings) -> tuple[list, list]:
    """Levels are on the UNDERLYING; option premium is read live."""
    picks, notes = [], []
    if ctx["bias"] == "Volatile":
        return [], [f"Option scalps skipped: {ctx['notes']}"]
    for i, (name, df) in enumerate(index_hist.items(), 1):
        df = df.dropna().sort_index()
        a, e20 = atr(df).iloc[-1], ema(df["Close"], 20).iloc[-1]
        last, ph, pl = df["Close"].iloc[-1], df["High"].iloc[-1], df["Low"].iloc[-1]
        gp = ctx.get("gap_pct")
        side = (1 if gp > 0.0005 else -1 if gp < -0.0005 else (1 if last > e20 else -1)) if gp is not None \
            else (1 if ctx["bias_score"] >= 0 and last > e20 else -1 if ctx["bias_score"] <= 0 and last < e20 else (1 if last > e20 else -1))
        risk = 0.18 * a
        entry = tick(ph if side > 0 else pl)
        step = INDEX_STEP[name]
        strike = int(round(entry / step) * step)
        weak = (gp is None) or abs(gp) <= 0.0005
        picks.append(_pick(
            id=f"{today:%Y%m%d}-S{i}", date=today.isoformat(), type="Option Scalp", symbol=name,
            direction="Buy" if side > 0 else "Sell", instrument="CE" if side > 0 else "PE",
            strike_expiry=f"{strike} / nearest liquid expiry", entry=entry,
            stop_loss=tick(entry - risk if side > 0 else entry + risk),
            target1=tick(entry + 1.6 * risk if side > 0 else entry - 1.6 * risk),
            target2=tick(entry + 2.4 * risk if side > 0 else entry - 2.4 * risk),
            confidence=2 if weak else 3, valid_until=today.isoformat(), signals=[], score=0,
            rationale=f"Levels are on the {name} index (not premium). Buy the {strike} {'CE' if side > 0 else 'PE'} only if the "
                      f"index trades {'above' if side > 0 else 'below'} {entry:.0f} after 9:30 and holds; exit by 14:45."
                      f"{' Weak gap signal.' if weak else ''}"))
    return picks, notes


def select_picks(cands: list, index_hist: dict, ctx: dict, today: dt.date, exclude: set, settings):
    k, bs = settings.picks_per_type, bias_sign(ctx)
    pool = [c for c in cands if c["symbol"] not in exclude]
    picks, notes = scalp_picks(index_hist, ctx, today, settings)

    # ----- Intraday: still allow both sides, ranked by directional score -----
    ranked = []
    for c in pool:
        ranked.append((c["momentum_score"] + (1 if bs > 0 else 0), 1, c))
        ranked.append((c["short_score"] + (1 if bs < 0 else 0), -1, c))
    ranked = [r for r in ranked if r[0] >= 2 and (r[2]["momentum_score"] if r[1] > 0 else r[2]["short_score"]) >= 1]
    ranked.sort(key=lambda r: (-r[0], -r[2]["turnover_cr"]))
    used, n = set(), 0
    for _, side, c in ranked:
        if n >= k:
            break
        if c["symbol"] in used:
            continue
        picks.append(intraday_pick(c, side, ctx, today, n + 1))
        used.add(c["symbol"])
        n += 1

    # ----- Short-term: high momentum + fundamental strength (long only) -----
    # Require meaningful momentum and prefer names that also have fund quality
    min_mom = getattr(settings, "min_momentum_score", 3)
    min_comp = getattr(settings, "min_composite", 3.5)
    quality = [
        c for c in pool
        if c["symbol"] not in used
        and c["momentum_score"] >= min_mom
        and c["composite"] >= min_comp
    ]
    # Rank: composite first, then pure momentum, then liquidity
    quality.sort(key=lambda c: (-c["composite"], -c["momentum_score"], -c["turnover_cr"]))
    n, sectors = 0, set()
    for c in quality:
        if n >= k:
            break
        if c["sector"] and c["sector"] in sectors:
            continue  # light sector diversification
        picks.append(short_term_pick(c, ctx, today, n + 1))
        sectors.add(c["sector"])
        n += 1

    if not quality:
        notes.append(f"No short-term candidates met mom>={min_mom} & composite>={min_comp}")

    good, rejected = [], []
    for p in picks:
        errs = validate_pick(p, settings.min_rr)
        (rejected if errs else good).append(errs or p)
    notes += [e for errs in rejected for e in errs]
    for t in ("Option Scalp", "Intraday", "Short-term"):
        if sum(1 for p in good if p["type"] == t) < k:
            notes.append(f"Only {sum(1 for p in good if p['type'] == t)} {t} pick(s) met the criteria today")
    return good, notes
