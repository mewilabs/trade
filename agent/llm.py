"""Claude is used for wording only (rationales, summary) and for a Gift Nifty web-search fallback.
Prices/levels are computed in code; the model is told never to change them."""
import json
import os
import re

SYSTEM = ("You write concise pre-market notes for an Indian-equities research tool. You receive JSON with market "
          "context and trade picks whose numbers are final. Do NOT change, add or invent any price, level or statistic. "
          "Return ONLY JSON: {\"summary\": str (max 60 words, plain English), \"rationales\": {pick_id: str (max 35 words, "
          "mention the key signals and one risk)}}. No advice language like 'guaranteed' or 'sure shot'.")


def _json(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else None


def template_notes(ctx: dict, picks: list) -> tuple[dict, str]:
    g = f"Gift Nifty implies {ctx['gap_pct']:+.2%} gap. " if ctx.get("gap_pct") is not None else "Gift Nifty unavailable. "
    return ({p["id"]: p["rationale"] for p in picks}, f"{g}Day bias: {ctx['bias']}.")


def narrate(settings, ctx: dict, picks: list) -> tuple[dict, str]:
    base, summary = template_notes(ctx, picks)
    if not os.getenv("ANTHROPIC_API_KEY") or not picks:
        return base, summary
    try:
        import anthropic
        slim = [{k: p.get(k) for k in ("id", "type", "symbol", "direction", "instrument", "entry", "stop_loss",
                                       "target1", "signals", "rationale")} for p in picks]
        msg = anthropic.Anthropic().messages.create(
            model=settings.model, max_tokens=1500, system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps({"context": ctx, "picks": slim}, default=str)}])
        data = _json("".join(b.text for b in msg.content if b.type == "text")) or {}
        rats = {k: v[:300] for k, v in (data.get("rationales") or {}).items() if isinstance(v, str)}
        return {**base, **{k: v for k, v in rats.items() if k in base}}, (data.get("summary") or summary)[:400]
    except Exception as e:  # never fail the run because of wording
        print(f"[llm] narrate fallback: {e}")
        return base, summary


def gift_nifty_via_search(settings):
    """Lower-reliability fallback: ask Claude to web-search the latest Gift Nifty price."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic
        msg = anthropic.Anthropic().messages.create(
            model=settings.model, max_tokens=600,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": "Find the latest GIFT Nifty (NSE IX) futures price right now. "
                       "Reply ONLY with JSON: {\"gift_nifty\": number or null, \"source\": string}."}])
        data = _json("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
        v = data.get("gift_nifty") if data else None
        return float(str(v).replace(",", "")) if v else None
    except Exception as e:
        print(f"[llm] gift nifty search failed: {e}")
        return None
