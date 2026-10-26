#!/usr/bin/env python3
"""Daily India market agent.  python main.py run [--demo] [--local] [--date YYYY-MM-DD] [--force] [--notify]"""
import argparse
import datetime as dt
import os
import sys

from agent import config, reconcile
from agent.context import build_context
from agent.data import DemoData, LiveData
from agent.llm import narrate
from agent.notify import telegram
from agent.picks import select_picks
from agent.report import build_report
from agent.scanner import analyze
from agent.store import make_store
from agent.tradingday import is_trading_day


def today_ist() -> dt.date:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)).date()


def run(args) -> str:
    s = config.load()
    today = dt.date.fromisoformat(args.date) if args.date else today_ist()
    if not args.force and not is_trading_day(today):
        return f"{today} is not an NSE trading day. Nothing to do."
    data = DemoData(today) if args.demo else LiveData(s)
    store = make_store(s, args.local or args.demo)

    rec_log = reconcile.run(store, s, data.history, today)

    index_hist = {n: data.history(n) for n in ("NIFTY", "BANKNIFTY")}
    nifty = index_hist["NIFTY"]["Close"]
    prev_close = float(nifty.iloc[-1])
    ctx = build_context(today, data.global_snapshot(), prev_close, data.gift_nifty(prev_close), s.vix_skip_scalp)

    universe = data.universe()
    symbols = list(universe)
    ohlcv = data.ohlcv(symbols)
    # Fundamentals are best-effort; missing data simply yields fund_score=0
    try:
        funds = data.fundamentals(symbols)
    except Exception:
        funds = {}
    cands = []
    for sym, df in ohlcv.items():
        c = analyze(sym, df, nifty, s.min_turnover_cr, universe.get(sym, ""), funds.get(sym))
        if c:
            cands.append(c)

    # Surface top momentum+quality names in notes for transparency
    top = sorted(cands, key=lambda x: (-x["composite"], -x["momentum_score"]))[:8]
    top_note = "Top momentum+quality: " + ", ".join(
        f"{c['symbol']}(m{c['momentum_score']}/f{c['fund_score']})" for c in top
    ) if top else "No strong candidates"

    picks, notes = select_picks(cands, index_hist, ctx, today, store.open_symbols(), s)
    rationales, summary = narrate(s, ctx, picks)
    for p in picks:
        p["rationale"] = rationales.get(p["id"], p["rationale"])

    store.add_market(ctx)
    store.add_picks(picks)
    text = build_report(
        ctx, picks,
        notes + [f"Scanned {len(cands)} liquid stocks", top_note],
        summary, rec_log, s.disclaimer,
    )
    os.makedirs(s.out_dir, exist_ok=True)
    open(os.path.join(s.out_dir, f"report_{today:%Y%m%d}.txt"), "w").write(text)
    if args.notify:
        telegram(text)
    return text


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run"])
    ap.add_argument("--demo", action="store_true", help="synthetic offline data, local storage")
    ap.add_argument("--local", action="store_true", help="store to out/store.json instead of Google Sheets")
    ap.add_argument("--date")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--notify", action="store_true")
    print(run(ap.parse_args()))
