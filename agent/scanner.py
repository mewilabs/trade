"""Nifty 500 scan: high-momentum + fundamental-quality scoring for short-term setups."""
import pandas as pd
from .indicators import ema, rsi, atr, roc, relative_strength


def _fund_score(fund: dict | None) -> tuple[int, list]:
    """Score fundamental quality from yfinance-style metrics. Returns (score 0-6, signals)."""
    if not fund:
        return 0, []
    score, sig = 0, []
    roe = fund.get("returnOnEquity")
    if roe is not None:
        if roe >= 0.18:
            score += 2
            sig.append(f"ROE {roe:.0%}")
        elif roe >= 0.12:
            score += 1
            sig.append(f"ROE {roe:.0%}")
    pm = fund.get("profitMargins")
    if pm is not None and pm > 0.12:
        score += 1
        sig.append(f"PM {pm:.0%}")
    de = fund.get("debtToEquity")
    if de is not None:
        # yfinance often reports as percentage-like number (e.g. 50 = 0.5)
        de_val = de / 100 if de > 5 else de
        if de_val < 0.5:
            score += 1
            sig.append("low debt")
        elif de_val > 1.5:
            score -= 1
    rg = fund.get("revenueGrowth") or fund.get("earningsGrowth")
    if rg is not None and rg > 0.12:
        score += 1
        sig.append(f"growth {rg:.0%}")
    pe = fund.get("trailingPE") or fund.get("forwardPE")
    if pe is not None and 8 < pe < 35:
        score += 1
        sig.append(f"PE {pe:.0f}")
    elif pe is not None and pe > 60:
        score -= 1
    return max(0, score), sig


def analyze(sym: str, df: pd.DataFrame, nifty_close: pd.Series, min_turnover_cr: float,
            sector: str = "", fund: dict | None = None) -> dict | None:
    """Score a stock for high momentum and fundamental strength. Returns candidate or None."""
    if df is None or len(df) < 210:
        return None
    df = df.dropna(subset=["Open", "High", "Low", "Close"]).sort_index()
    c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
    turnover_cr = (c * v).rolling(20).mean().iloc[-1] / 1e7
    if not turnover_cr or turnover_cr < min_turnover_cr:
        return None

    e20, e50, e200 = ema(c, 20), ema(c, 50), ema(c, 200)
    r = rsi(c)
    a = atr(df)
    last = float(c.iloc[-1])
    if pd.isna(a.iloc[-1]) or pd.isna(r.iloc[-1]) or pd.isna(e200.iloc[-1]):
        return None

    hi20 = float(h.rolling(20).max().shift(1).iloc[-1])
    lo20 = float(l.rolling(20).min().shift(1).iloc[-1])
    n52 = min(252, len(df))
    hi52, lo52 = float(h.iloc[-n52:].max()), float(l.iloc[-n52:].min())
    vol_ma20 = float(v.rolling(20).mean().iloc[-1])
    vol_ratio = float(v.iloc[-1] / vol_ma20) if vol_ma20 else 1.0
    ret5 = float(c.iloc[-1] / c.iloc[-6] - 1)
    ret10 = float(roc(c, 10).iloc[-1]) if len(c) > 11 else 0.0
    ret20 = float(roc(c, 20).iloc[-1]) if len(c) > 21 else 0.0
    rs20 = relative_strength(c, nifty_close, 20) if nifty_close is not None and len(nifty_close) > 21 else 0.0

    up_stack = e20.iloc[-1] > e50.iloc[-1] > e200.iloc[-1]
    dn_stack = e20.iloc[-1] < e50.iloc[-1] < e200.iloc[-1]
    near20 = abs(last / e20.iloc[-1] - 1) < 0.03
    above_all = last > e20.iloc[-1] > e50.iloc[-1] > e200.iloc[-1]

    # ----- High momentum signals (long bias for short-term) -----
    mom_sig = []
    mom_score = 0

    if ret5 > 0.03:
        mom_score += 1
        mom_sig.append(f"5d +{ret5:.1%}")
    if ret10 > 0.05:
        mom_score += 1
        mom_sig.append(f"10d +{ret10:.1%}")
    if ret20 > 0.08:
        mom_score += 1
        mom_sig.append(f"20d +{ret20:.1%}")
    if rs20 > 0.03:
        mom_score += 2
        mom_sig.append(f"RS+{rs20:.1%} vs Nifty")
    elif rs20 > 0.01:
        mom_score += 1
        mom_sig.append(f"RS+{rs20:.1%} vs Nifty")
    if last >= hi20 and vol_ratio > 1.4:
        mom_score += 2
        mom_sig.append("20d breakout + vol")
    elif last >= hi20:
        mom_score += 1
        mom_sig.append("20d high")
    if last >= 0.97 * hi52:
        mom_score += 1
        mom_sig.append("near 52w high")
    if above_all:
        mom_score += 1
        mom_sig.append("above EMA stack")
    if up_stack and near20:
        mom_score += 1
        mom_sig.append("pullback in uptrend")
    if 55 <= r.iloc[-1] <= 75:
        mom_score += 1
        mom_sig.append(f"RSI {r.iloc[-1]:.0f} momentum")
    if vol_ratio > 1.8:
        mom_score += 1
        mom_sig.append(f"vol {vol_ratio:.1f}x")

    # Oversold bounce (secondary)
    if r.iloc[-1] < 35 and r.iloc[-1] > r.iloc[-2] and up_stack:
        mom_score += 1
        mom_sig.append("oversold turn in uptrend")

    # ----- Short / weak signals (kept for intraday shorts) -----
    short_sig, short_score = [], 0
    if last <= lo20 and vol_ratio > 1.5:
        short_score += 2
        short_sig.append("20d breakdown on volume")
    if last <= 1.03 * lo52:
        short_score += 1
        short_sig.append("near 52w low")
    if dn_stack and near20:
        short_score += 1
        short_sig.append("rally in downtrend")
    if 30 <= r.iloc[-1] <= 45:
        short_score += 1
        short_sig.append(f"RSI {r.iloc[-1]:.0f} weak")
    if rs20 < -0.03:
        short_score += 1
        short_sig.append(f"RS{rs20:.1%} lagging")

    fund_score, fund_sig = _fund_score(fund)
    # Composite prioritises momentum; fundamentals act as quality filter / boost
    composite = mom_score + fund_score * 0.75

    return {
        "symbol": sym,
        "sector": sector,
        "close": last,
        "prev_high": float(h.iloc[-1]),
        "prev_low": float(l.iloc[-1]),
        "atr": float(a.iloc[-1]),
        "ema20": float(e20.iloc[-1]),
        "rsi": float(r.iloc[-1]),
        "swing_low10": float(l.iloc[-10:].min()),
        "swing_high10": float(h.iloc[-10:].max()),
        "turnover_cr": float(turnover_cr),
        "ret5": ret5,
        "ret10": ret10,
        "ret20": ret20,
        "rs20": rs20,
        "vol_ratio": vol_ratio,
        "long_score": mom_score,          # kept for backward compat
        "short_score": short_score,
        "momentum_score": mom_score,
        "fund_score": fund_score,
        "composite": composite,
        "long_signals": mom_sig,
        "short_signals": short_sig,
        "fund_signals": fund_sig,
    }
