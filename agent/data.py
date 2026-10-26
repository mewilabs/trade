"""Data providers. LiveData uses yfinance/NSE archives; DemoData is offline and deterministic."""
import datetime as dt
import io
import json
import os
import re
import numpy as np
import pandas as pd

INDEX_TICKERS = {"NIFTY": "^NSEI", "BANKNIFTY": "^NSEBANK"}
GLOBAL_TICKERS = {"spx": "^GSPC", "nasdaq": "^IXIC", "dow": "^DJI", "nikkei": "^N225", "hangseng": "^HSI",
                  "crude": "BZ=F", "usdinr": "INR=X", "india_vix": "^INDIAVIX", "us_vix": "^VIX"}
NSE_LIST_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"]).copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df.sort_index()


class LiveData:
    def __init__(self, settings):
        self.s = settings

    def universe(self) -> dict:
        import requests
        cache = "data/nifty500.csv"
        try:
            r = requests.get(NSE_LIST_URL, headers=UA, timeout=30)
            r.raise_for_status()
            os.makedirs("data", exist_ok=True)
            open(cache, "wb").write(r.content)
            raw = r.content
        except Exception:
            if not os.path.exists(cache):
                raise RuntimeError("Could not download the Nifty 500 list; place it at data/nifty500.csv")
            raw = open(cache, "rb").read()
        df = pd.read_csv(io.BytesIO(raw))
        return dict(zip(df["Symbol"].str.strip(), df["Industry"].fillna("")))

    def ohlcv(self, symbols: list) -> dict:
        import yfinance as yf
        out = {}
        for i in range(0, len(symbols), 100):
            chunk = symbols[i:i + 100]
            data = yf.download([f"{s}.NS" for s in chunk], period="14mo", interval="1d", group_by="ticker",
                               auto_adjust=True, threads=True, progress=False)
            for s in chunk:
                try:
                    d = _clean(data[f"{s}.NS"])
                    if len(d):
                        out[s] = d
                except Exception:
                    continue
        return out

    def fundamentals(self, symbols: list) -> dict:
        """Best-effort fundamental snapshot via yfinance.info. Many NSE names have sparse data."""
        import yfinance as yf
        keys = ("returnOnEquity", "profitMargins", "debtToEquity", "revenueGrowth",
                "earningsGrowth", "trailingPE", "forwardPE", "marketCap")
        out = {}
        for s in symbols:
            try:
                info = yf.Ticker(f"{s}.NS").info or {}
                snap = {k: info.get(k) for k in keys if info.get(k) is not None}
                if snap:
                    out[s] = snap
            except Exception:
                continue
        return out

    def history(self, symbol: str, days: int = 400) -> pd.DataFrame:
        import yfinance as yf
        t = INDEX_TICKERS.get(symbol, f"{symbol}.NS")
        return _clean(yf.download(t, period="2y" if days > 200 else "6mo", interval="1d", auto_adjust=True, progress=False,
                                  multi_level_index=False))

    def global_snapshot(self) -> dict:
        import yfinance as yf
        out = {}
        for k, t in GLOBAL_TICKERS.items():
            try:
                d = yf.download(t, period="10d", interval="1d", progress=False, auto_adjust=True, multi_level_index=False)["Close"].dropna()
                out[k] = float(d.iloc[-1]) if k in ("india_vix", "us_vix", "usdinr") else float(d.iloc[-1] / d.iloc[-2] - 1)
            except Exception:
                out[k] = None
        return out

    def gift_nifty(self, nifty_prev_close: float):
        """Order: manual override -> your JSON URL -> Claude web search. Returns None if nothing passes sanity check."""
        def ok(v):
            return v if v and abs(v / nifty_prev_close - 1) < 0.03 else None
        if os.getenv("GIFT_NIFTY_OVERRIDE"):
            return ok(float(os.environ["GIFT_NIFTY_OVERRIDE"]))
        url, path = os.getenv("GIFT_NIFTY_URL"), os.getenv("GIFT_NIFTY_JSON_PATH", "")
        if url:
            try:
                import requests
                node = requests.get(url, headers=UA, timeout=20).json()
                for part in filter(None, path.split(".")):
                    node = node[int(part)] if part.isdigit() else node[part]
                return ok(float(str(node).replace(",", "")))
            except Exception:
                pass
        from .llm import gift_nifty_via_search
        return ok(gift_nifty_via_search(self.s))


class DemoData:
    """Offline synthetic market so the whole pipeline can be exercised without network."""
    N = 700

    def __init__(self, today: dt.date, seed: int = 7):
        self.today, self.seed = today, seed
        self.dates = pd.bdate_range("2023-06-01", periods=self.N)

    def _series(self, key: str, start: float, vol: float, drift: float) -> pd.DataFrame:
        rng = np.random.default_rng(int.from_bytes(f"{key}{self.seed}".encode(), "little") % (2**32))
        r = rng.normal(drift, vol, self.N)
        c = start * np.exp(np.cumsum(r))
        o = np.r_[start, c[:-1]] * (1 + rng.normal(0, vol / 4, self.N))
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, vol / 3, self.N)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, vol / 3, self.N)))
        v = rng.lognormal(13.5, 0.5, self.N)
        df = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v}, index=self.dates)
        return df[df.index.date < self.today]

    def universe(self) -> dict:
        sectors = ["IT", "Banks", "Auto", "Pharma", "Metals", "FMCG", "Energy", "Infra"]
        return {f"DEMO{i:03d}": sectors[i % len(sectors)] for i in range(80)}

    def ohlcv(self, symbols):
        rng = np.random.default_rng(self.seed)
        return {s: self._series(s, float(rng.uniform(100, 3000)), 0.016, float(rng.uniform(-0.0005, 0.0025))) for s in symbols}

    def history(self, symbol, days=400):
        if symbol == "NIFTY": return self._series("NIFTY", 18000, 0.008, 0.0005)
        if symbol == "BANKNIFTY": return self._series("BANKNIFTY", 40000, 0.010, 0.0004)
        rng = np.random.default_rng(self.seed)
        syms = list(self.universe())
        i = syms.index(symbol) if symbol in syms else 0
        return self.ohlcv(syms)[syms[i]] if symbol in syms else self._series(symbol, 500, 0.016, 0.0)

    def global_snapshot(self):
        return {"spx": 0.006, "nasdaq": 0.009, "dow": 0.003, "nikkei": 0.004, "hangseng": -0.002,
                "crude": -0.01, "usdinr": 85.1, "india_vix": 13.8, "us_vix": 15.9}

    def gift_nifty(self, nifty_prev_close):
        return round(nifty_prev_close * 1.0035, 1)

    def fundamentals(self, symbols: list) -> dict:
        """Synthetic quality metrics so demo pipeline exercises fund scoring."""
        rng = np.random.default_rng(self.seed + 11)
        out = {}
        for s in symbols:
            out[s] = {
                "returnOnEquity": float(rng.uniform(0.08, 0.28)),
                "profitMargins": float(rng.uniform(0.05, 0.22)),
                "debtToEquity": float(rng.uniform(10, 120)),  # yfinance-style %
                "revenueGrowth": float(rng.uniform(-0.05, 0.25)),
                "trailingPE": float(rng.uniform(12, 45)),
            }
        return out
