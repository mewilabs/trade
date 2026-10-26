import os
from dataclasses import dataclass


def _f(name, default):
    return float(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    capital: float = _f("CAPITAL", 500000)
    risk_pct: float = _f("RISK_PCT", 0.01)
    min_rr: float = _f("MIN_RR", 1.5)
    picks_per_type: int = 2
    max_hold_days: int = 10
    short_term_entry_valid_days: int = 3
    min_turnover_cr: float = _f("MIN_TURNOVER_CR", 20)
    vix_skip_scalp: float = _f("VIX_SKIP_SCALP", 22)
    min_momentum_score: int = int(_f("MIN_MOMENTUM_SCORE", 3))
    min_composite: float = _f("MIN_COMPOSITE", 3.5)
    allow_short_term_shorts: bool = False  # delivery shorts are not possible in cash
    model: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")
    sheet_id: str = os.getenv("SHEET_ID", "")
    out_dir: str = os.getenv("OUT_DIR", "out")
    disclaimer: str = ("Research/education only, not investment advice. Intraday and options "
                       "trading can cause substantial losses.")


def load() -> Settings:
    return Settings()
