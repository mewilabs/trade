"""Settle earlier picks against daily OHLC. Conservative: if SL and target are both touched in one candle, SL wins."""
import datetime as dt
import pandas as pd


def evaluate(pos: dict, bars: pd.DataFrame, max_hold_days: int = 10, entry_valid_days: int = 3):
    """Return an update dict for the tracker, or None if there is nothing new to record.
    pos keys: type, direction, entry, stop_loss, target1, target2, actual_entry, date, valid_until."""
    long = pos["direction"] == "Buy"
    e, sl, t1, t2 = pos["entry"], pos["stop_loss"], pos["target1"], pos.get("target2") or pos["target1"]
    same_day = pos["type"] in ("Intraday", "Option Scalp")
    bars = bars[bars.index.date >= pos["date"]]
    if same_day:
        bars = bars[bars.index.date == pos["date"]]
    if bars.empty:
        return None
    filled = pos.get("actual_entry")
    held, upd = 0, {}
    for ts, b in bars.iterrows():
        d = ts.date()
        o, h, l, c = b["Open"], b["High"], b["Low"], b["Close"]
        if filled is None:
            if d > pos["valid_until"]:
                return {"status": "Not Triggered", "notes": "Entry never triggered within validity"}
            if (long and h >= e) or (not long and l <= e):
                filled = max(o, e) if long else min(o, e)
                upd.update(actual_entry=round(float(filled), 2), notes="Filled at entry/open (daily-bar approximation)")
            else:
                continue
        held += 1
        hit_sl = l <= sl if long else h >= sl
        hit_t2 = h >= t2 if long else l <= t2
        hit_t1 = h >= t1 if long else l <= t1
        note = upd.get("notes", "")
        if hit_sl:
            if hit_t1 or hit_t2:
                note += "; SL and target both touched in one candle, SL assumed first"
            return {**upd, "status": "SL Hit", "exit_price": round(float(sl), 2), "exit_date": d.isoformat(), "notes": note}
        if hit_t2:
            return {**upd, "status": "T2 Hit", "exit_price": round(float(t2), 2), "exit_date": d.isoformat(), "notes": note}
        if hit_t1:
            return {**upd, "status": "T1 Hit", "exit_price": round(float(t1), 2), "exit_date": d.isoformat(), "notes": note}
        if same_day or held >= max_hold_days:
            return {**upd, "status": "Expired", "exit_price": round(float(c), 2), "exit_date": d.isoformat(),
                    "notes": upd.get("notes", "") + ("; squared off at close" if same_day else "; max holding period reached")}
    if filled is None and (same_day or bars.index[-1].date() >= pos["valid_until"]):
        return {"status": "Not Triggered", "notes": "Entry never triggered within validity"}
    return upd or None


def run(store, settings, fetch_history, today: dt.date) -> list:
    log = []
    for pos in store.open_positions():
        if pos["date"] >= today:
            continue
        try:
            upd = evaluate(pos, fetch_history(pos["symbol"]), settings.max_hold_days, settings.short_term_entry_valid_days)
        except Exception as e:
            log.append(f"{pos['id']}: reconcile failed ({e})")
            continue
        if upd:
            store.update_tracker(pos["id"], upd)
            log.append(f"{pos['id']} {pos['symbol']}: {upd.get('status', 'Open (filled)')}")
    return log
