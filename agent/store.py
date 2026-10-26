"""Storage backends with one interface: LocalStore (JSON) and SheetsStore (Google Sheets)."""
import datetime as dt
import json
import os


def to_date(v):
    if isinstance(v, dt.date):
        return v
    if isinstance(v, (int, float)) and v > 20000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    if isinstance(v, str) and v.strip():
        try:
            return dt.date.fromisoformat(v.strip()[:10])
        except ValueError:
            from dateutil import parser
            return parser.parse(v, dayfirst=True).date()
    return None


def num(v):
    try:
        return float(str(v).replace(",", "")) if str(v).strip() != "" else None
    except ValueError:
        return None


class LocalStore:
    def __init__(self, out_dir="out"):
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, "store.json")
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {"market": [], "reco": [], "tracker": []}

    def _save(self):
        json.dump(self.d, open(self.path, "w"), indent=1, default=str)

    def add_market(self, ctx):
        self.d["market"] = [m for m in self.d["market"] if m["date"] != ctx["date"]] + [ctx]; self._save()

    def add_picks(self, picks):
        ids = {p["id"] for p in picks}
        self.d["reco"] = [r for r in self.d["reco"] if r["id"] not in ids] + picks
        self.d["tracker"] = [t for t in self.d["tracker"] if t["id"] not in ids] + [
            {"id": p["id"], "date": p["date"], "type": p["type"], "symbol": p["symbol"], "direction": p["direction"],
             "entry": p["entry"], "stop_loss": p["stop_loss"], "target1": p["target1"], "actual_entry": None,
             "exit_price": None, "exit_date": None, "status": "Open", "notes": ""} for p in picks]
        self._save()

    def open_positions(self):
        reco = {r["id"]: r for r in self.d["reco"]}
        out = []
        for t in self.d["tracker"]:
            if t["status"] == "Open" and t["id"] in reco:
                r = reco[t["id"]]
                out.append({**t, "date": to_date(t["date"]), "target2": r["target2"], "instrument": r["instrument"],
                            "valid_until": to_date(r["valid_until"])})
        return out

    def update_tracker(self, pid, u):
        for t in self.d["tracker"]:
            if t["id"] == pid:
                t.update(u)
        self._save()

    def open_symbols(self):
        return {t["symbol"] for t in self.d["tracker"] if t["status"] == "Open"}


class SheetsStore:
    """Writes only to input cells; formula columns (Recommendations L:M, Tracker M:P, Market_Context D:E) are untouched."""

    def __init__(self, sheet_id, sa_json=None, sa_file=None):
        import gspread
        gc = gspread.service_account_from_dict(json.loads(sa_json)) if sa_json else gspread.service_account(filename=sa_file)
        sh = gc.open_by_key(sheet_id)
        self.mc, self.rc, self.tr = (sh.worksheet(n) for n in ("Market_Context", "Recommendations", "Tracker"))

    @staticmethod
    def _next(ws):
        return len(ws.col_values(1)) + 1

    @staticmethod
    def _put(ws, row, blocks):
        ws.batch_update([{"range": f"{a}{row}:{b}{row}", "values": [vals]} for a, b, vals in blocks],
                        value_input_option="USER_ENTERED")

    def add_market(self, c):
        r = self._next(self.mc)
        if str(self.mc.cell(r - 1, 1).value) == c["date"]:
            r -= 1  # same-day rerun overwrites
        g = lambda k: "" if c.get(k) is None else c[k]
        self._put(self.mc, r, [("A", "C", [c["date"], g("gift_nifty"), g("nifty_prev_close")]),
                               ("F", "P", [g("spx"), g("nasdaq"), g("dow"), g("nikkei"), g("hangseng"), g("crude"),
                                           g("usdinr"), g("india_vix"), g("us_vix"), c["bias"], c["notes"]])])

    def add_picks(self, picks):
        have = set(self.rc.col_values(1))
        picks = [p for p in picks if p["id"] not in have]  # idempotent reruns
        r, t = self._next(self.rc), self._next(self.tr)
        for i, p in enumerate(picks):
            self._put(self.rc, r + i, [
                ("A", "K", [p["id"], p["date"], p["type"], p["symbol"], p["direction"], p["instrument"],
                            p["strike_expiry"], p["entry"], p["stop_loss"], p["target1"], p["target2"]]),
                ("N", "P", [p["rationale"], p["confidence"], p["valid_until"]])])
            self._put(self.tr, t + i, [
                ("A", "H", [p["id"], p["date"], p["type"], p["symbol"], p["direction"], p["entry"], p["stop_loss"], p["target1"]]),
                ("L", "L", ["Open"])])

    def _rows(self, ws):
        vals = ws.get_all_values(value_render_option="UNFORMATTED_VALUE")
        hdr = vals[0]
        return [(i, dict(zip(hdr, row))) for i, row in enumerate(vals[1:], 2) if row and row[0] != ""]

    def open_positions(self):
        reco = {r["ID"]: r for _, r in self._rows(self.rc)}
        out = []
        for i, t in self._rows(self.tr):
            if t.get("Status") != "Open" or "EXAMPLE" in str(t.get("Notes", "")) or t["ID"] not in reco:
                continue
            r = reco[t["ID"]]
            out.append({"id": t["ID"], "row": i, "date": to_date(t["Date"]), "type": t["Type"], "symbol": t["Symbol"],
                        "direction": t["Direction"], "entry": num(t["Planned Entry"]), "stop_loss": num(t["Stop Loss"]),
                        "target1": num(t["Target 1"]), "actual_entry": num(t["Actual Entry"]), "status": "Open",
                        "target2": num(r["Target 2"]), "instrument": r["Instrument"], "valid_until": to_date(r["Valid Until"])})
        return out

    def update_tracker(self, pid, u):
        row = self.tr.col_values(1).index(pid) + 1
        cols = {"actual_entry": "I", "exit_price": "J", "exit_date": "K", "status": "L", "notes": "Q"}
        self.tr.batch_update([{"range": f"{cols[k]}{row}", "values": [[v if v is not None else ""]]} for k, v in u.items() if k in cols],
                             value_input_option="USER_ENTERED")

    def open_symbols(self):
        return {p["symbol"] for p in self.open_positions()}


def make_store(settings, local: bool):
    if local or not settings.sheet_id:
        return LocalStore(settings.out_dir)
    return SheetsStore(settings.sheet_id, os.getenv("GOOGLE_SA_JSON"), os.getenv("GOOGLE_SA_FILE"))
