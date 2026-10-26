import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up, dn = d.clip(lower=0), -d.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    out = 100 - 100 / (1 + au / ad.replace(0, np.nan))
    out[(ad == 0) & au.notna()] = 100.0
    return out


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def roc(close: pd.Series, n: int) -> pd.Series:
    """Rate of change as fraction (e.g. 0.05 = +5%)."""
    return close / close.shift(n) - 1


def relative_strength(stock_close: pd.Series, index_close: pd.Series, n: int = 20) -> float:
    """Stock return over n periods minus index return over same period."""
    if len(stock_close) < n + 1 or len(index_close) < n + 1:
        return 0.0
    s_ret = float(stock_close.iloc[-1] / stock_close.iloc[-n - 1] - 1)
    i_ret = float(index_close.iloc[-1] / index_close.iloc[-n - 1] - 1)
    return s_ret - i_ret
