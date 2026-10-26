import datetime as dt
import json
import types

import numpy as np
import pandas as pd
import pytest

from agent.indicators import atr, rsi
from agent.reconcile import evaluate
from agent.validate import validate_pick


def bars(rows, start="2026-01-06"):
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx).assign(Volume=1)


def pos(**kw):
    base = dict(type="Intraday", direction="Buy", entry=100, stop_loss=95, target1=108, target2=112,
                actual_entry=None, date=dt.date(2026, 1, 6), valid_until=dt.date(2026, 1, 6))
    return {**base, **kw}


def test_rsi_atr_sane():
    s = pd.Series(np.linspace(100, 150, 60))
    assert rsi(s).iloc[-1] == 100.0
    df = pd.DataFrame({"High": s + 1, "Low": s - 1, "Close": s})
    assert 1.9 < atr(df).iloc[-1] < 2.1


def test_validate():
    ok = dict(symbol="X", direction="Buy", entry=100, stop_loss=95, target1=108)
    assert validate_pick(ok) == []
    assert validate_pick({**ok, "target1": 104})            # rr 0.8
    assert validate_pick({**ok, "stop_loss": 105})          # wrong side
    assert validate_pick({**ok, "stop_loss": None})         # missing
    sell = dict(symbol="X", direction="Sell", entry=100, stop_loss=105, target1=92)
    assert validate_pick(sell) == []


def test_long_target_hit():
    u = evaluate(pos(), bars([[99, 109, 98, 108]]))
    assert u["status"] == "T1 Hit" and u["exit_price"] == 108 and u["actual_entry"] == 100


def test_long_stop_hit_and_same_candle_is_conservative():
    assert evaluate(pos(), bars([[99, 101, 94, 96]]))["status"] == "SL Hit"
    u = evaluate(pos(), bars([[99, 110, 94, 105]]))
    assert u["status"] == "SL Hit" and "SL assumed first" in u["notes"]


def test_gap_up_fills_at_open():
    u = evaluate(pos(), bars([[103, 105, 101, 104]]))
    assert u["actual_entry"] == 103 and u["status"] == "Expired" and u["exit_price"] == 104


def test_not_triggered_and_intraday_squareoff():
    assert evaluate(pos(), bars([[97, 99, 96, 98]]))["status"] == "Not Triggered"
    u = evaluate(pos(), bars([[99, 104, 98, 102]]))
    assert u["status"] == "Expired" and u["exit_price"] == 102


def test_short_side():
    p = pos(direction="Sell", entry=100, stop_loss=105, target1=92, target2=88)
    assert evaluate(p, bars([[101, 102, 91, 92]]))["status"] == "T1 Hit"
    assert evaluate(p, bars([[101, 106, 99, 104]]))["status"] == "SL Hit"


def test_short_term_waits_then_fills_and_expires():
    p = pos(type="Short-term", valid_until=dt.date(2026, 1, 9))
    rows = [[97, 99, 96, 98], [98, 101, 97, 100]]  # fills day 2, nothing else yet
    u = evaluate(p, bars(rows))
    assert u["actual_entry"] == 100 and "status" not in u
    p2 = {**p, "actual_entry": 100}
    long_rows = [[100, 103, 99, 101]] * 10
    assert evaluate(p2, bars(long_rows), max_hold_days=10)["status"] == "Expired"


def test_demo_pipeline_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import main
    args = types.SimpleNamespace(demo=True, local=True, date="2026-01-06", force=True, notify=False)
    text = main.run(args)
    d = json.load(open("out/store.json"))
    assert {p["type"] for p in d["reco"]} == {"Option Scalp", "Intraday", "Short-term"}
    assert all(validate_pick(p) == [] for p in d["reco"])
    assert len(d["reco"]) <= 6 and "not investment advice" in text
    n = len(d["reco"])
    main.run(args)                                           # same-day rerun must not duplicate
    assert len(json.load(open("out/store.json"))["reco"]) == n
    args.date = "2026-01-07"
    assert "Updated from earlier picks" in main.run(args)    # next day reconciles yesterday
