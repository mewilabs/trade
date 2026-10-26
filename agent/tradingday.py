import datetime as dt
import os


def _extra_holidays(path="data/holidays.txt"):
    if not os.path.exists(path):
        return set()
    out = set()
    for line in open(path):
        line = line.split("#")[0].strip()
        if line:
            out.add(dt.date.fromisoformat(line))
    return out


def is_trading_day(d: dt.date) -> bool:
    """Best effort: weekends, data/holidays.txt, then BSE calendar (XBOM) as a proxy for NSE."""
    if d.weekday() >= 5 or d in _extra_holidays():
        return False
    try:
        import exchange_calendars as xc
        import pandas as pd
        return bool(xc.get_calendar("XBOM").is_session(pd.Timestamp(d)))
    except Exception:
        return True
