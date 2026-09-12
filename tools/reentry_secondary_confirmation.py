#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
import math
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")


def finite(value) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except Exception:
        return False


def ticker_close(frame: pd.DataFrame, ticker: str) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        try:
            return pd.to_numeric(frame["Close"][ticker], errors="coerce").dropna()
        except Exception:
            try:
                return pd.to_numeric(frame[ticker]["Close"], errors="coerce").dropna()
            except Exception:
                return pd.Series(dtype=float)
    if "Close" in frame.columns:
        return pd.to_numeric(frame["Close"], errors="coerce").dropna()
    return pd.Series(dtype=float)


def pct_change(series: pd.Series, sessions: int = 5) -> float | None:
    if len(series) <= sessions:
        return None
    a, b = float(series.iloc[-1]), float(series.iloc[-1 - sessions])
    return a / b - 1.0 if b else None


def vix_term_structure() -> dict:
    raw = yf.download(["^VIX", "^VIX3M"], period="1mo", interval="1d", auto_adjust=False,
                      progress=False, threads=False, group_by="column", timeout=25)
    vix, vix3m = ticker_close(raw, "^VIX"), ticker_close(raw, "^VIX3M")
    aligned = pd.concat([vix.rename("VIX"), vix3m.rename("VIX3M")], axis=1).dropna()
    if len(aligned) < 2:
        raise ValueError("Insufficient VIX/VIX3M history")
    ratio = aligned["VIX"] / aligned["VIX3M"]
    current, prior = float(ratio.iloc[-1]), float(ratio.iloc[-2])
    if current > 1.10:
        state = "ACUTE_STRESS"
    elif current > 1.00:
        state = "BACKWARDATION"
    elif prior > 1.00 and current <= 1.00:
        state = "NORMALIZING"
    elif current <= 0.97:
        state = "NORMALIZED"
    else:
        state = "NEAR_NORMAL"
    normalization_cross = prior > 1.0 and current <= 1.0
    supportive = current <= 1.0 or (prior > 1.0 and current < prior)
    return {
        "name": "VIX term-structure repair",
        "state": state,
        "supportive": supportive,
        "current_ratio": current,
        "prior_ratio": prior,
        "change": current - prior,
        "normalization_cross": normalization_cross,
        "benchmark": ">1.10 acute inversion · >1.00 backwardation/stress · cross back below 1.00 normalization · <0.97 normalized contango",
        "retail_explanation": "This asks whether near-term market fear is still unusually intense or starting to calm down. A move back below 1.00 is generally a healthier sign for a rebound.",
        "source": "Yahoo Finance daily ^VIX and ^VIX3M; Cboe term-structure methodology",
        "validation_status": "VALIDATED_EVENT_SUPPORT",
        "validation_note": "Frozen 2007-2026 falsification found QQQ 10D after VIX/VIX3M normalization below 1.00: n=78, median +2.17%, positive 69.2%, matched excess +1.17%; workflow run 33811926596.",
    }


def breadth_thrust(values: dict) -> dict:
    adv, dec = values.get("NAADV"), values.get("NADEC")
    total = float(adv) + float(dec) if finite(adv) and finite(dec) else None
    ratio = float(adv) / total if total and total > 0 else None
    if ratio is None:
        state = "UNAVAILABLE"
        supportive = False
    elif ratio >= 0.615:
        state = "THRUST_LEVEL"
        supportive = True
    elif ratio >= 0.55:
        state = "BUILDING"
        supportive = True
    elif ratio >= 0.45:
        state = "MIXED"
        supportive = False
    else:
        state = "DEFENSIVE"
        supportive = False
    return {
        "name": "Breadth participation thrust",
        "state": state,
        "supportive": supportive,
        "nasdaq_advance_share": ratio,
        "advancing_issues": float(adv) if finite(adv) else None,
        "declining_issues": float(dec) if finite(dec) else None,
        "benchmark": "<45% defensive · 45-55% mixed · 55-61.5% building · >=61.5% strong thrust-level participation",
        "retail_explanation": "This checks whether the rebound is spreading across lots of stocks instead of being carried by just a few big names. More participation usually makes a recovery more convincing.",
        "source": "Current Nasdaq advancing/declining issues already captured by RE-ENTRY",
        "validation_status": "RESEARCH_PENDING",
        "validation_note": "61.5% is a classic Zweig breadth-thrust reference, but a true Zweig signal also requires a move from below 40% within 10 sessions. This live level is not labeled a classic Zweig confirmation until history proves the path condition.",
    }


def risk_appetite() -> dict:
    tickers = ["RSP", "SPY", "IWM", "HYG", "LQD"]
    raw = yf.download(tickers, period="2mo", interval="1d", auto_adjust=True,
                      progress=False, threads=True, group_by="column", timeout=30)
    px = {t: ticker_close(raw, t) for t in tickers}
    common = None
    for s in px.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 7:
        raise ValueError("Insufficient risk-appetite history")
    def rel(a: str, b: str) -> tuple[float, float | None]:
        ratio = (px[a].reindex(common) / px[b].reindex(common)).dropna()
        return float(ratio.iloc[-1]), pct_change(ratio, 5)
    rsp_spy, rsp5 = rel("RSP", "SPY")
    iwm_spy, iwm5 = rel("IWM", "SPY")
    hyg_lqd, credit5 = rel("HYG", "LQD")
    components = {
        "equal_weight_broadening": bool(rsp5 is not None and rsp5 > 0),
        "small_caps_confirming": bool(iwm5 is not None and iwm5 > 0),
        "credit_risk_appetite": bool(credit5 is not None and credit5 > 0),
    }
    count = sum(components.values())
    state = ["DEFENSIVE", "MIXED", "BROADENING", "BROAD_RISK_ON"][count]
    return {
        "name": "Risk-appetite broadening",
        "state": state,
        "supportive": count >= 2,
        "supportive_components": count,
        "components": components,
        "RSP_SPY": rsp_spy,
        "RSP_SPY_5d_change": rsp5,
        "IWM_SPY": iwm_spy,
        "IWM_SPY_5d_change": iwm5,
        "HYG_LQD": hyg_lqd,
        "HYG_LQD_5d_change": credit5,
        "benchmark": "0/3 defensive · 1/3 mixed · 2/3 broadening · 3/3 broad risk-on; each component requires positive 5-session relative momentum",
        "retail_explanation": "This checks whether investors are moving beyond the safest and biggest stocks into equal-weight stocks, small caps, and lower-quality credit. That usually means confidence is returning more broadly.",
        "source": "Yahoo Finance daily adjusted closes: RSP/SPY, IWM/SPY, HYG/LQD",
        "validation_status": "RESEARCH_PENDING",
        "validation_note": "Composite is deliberately one family, not three votes. Historical conditional validation is required before it can affect recovery-stage grading.",
    }


def cboe_put_call(market_date: str) -> dict:
    query = urlencode({"dt": market_date})
    url = f"https://www.cboe.com/markets/us/options/market-statistics/daily?{query}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY-secondary-confirmation/1.0"})
    with urlopen(req, timeout=25) as resp:  # nosec - fixed Cboe HTTPS endpoint
        raw = resp.read().decode("utf-8", errors="replace")
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text)
    def extract(label: str) -> float | None:
        match = re.search(re.escape(label) + r"\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
        return float(match.group(1)) if match else None
    equity = extract("EQUITY PUT/CALL RATIO")
    index = extract("INDEX PUT/CALL RATIO")
    total = extract("TOTAL PUT/CALL RATIO")
    if equity is None and index is None:
        raise ValueError("Cboe page did not expose put/call ratios")
    if equity is None:
        state = "UNAVAILABLE"
    elif equity >= 0.90:
        state = "HIGH_FEAR"
    elif equity >= 0.70:
        state = "FEAR"
    elif equity >= 0.50:
        state = "NORMAL"
    else:
        state = "COMPLACENT"
    return {
        "name": "Options sentiment",
        "state": state,
        "supportive": False,
        "equity_put_call": equity,
        "index_put_call": index,
        "total_put_call": total,
        "benchmark": "Heuristic display scale only until rolling percentiles mature: equity P/C <0.50 complacent · 0.50-0.70 normal · 0.70-0.90 fear · >=0.90 high fear",
        "retail_explanation": "This looks at how heavily traders are using puts versus calls. High put activity often means fear is elevated; the useful part for RE-ENTRY is whether that fear later starts to unwind.",
        "source": "Cboe U.S. Options Daily Market Statistics",
        "validation_status": "RESEARCH_PENDING",
        "validation_note": "Cboe cautions that put/call ratios can be distorted by product mix and exercise-related flow. Equity and index ratios are kept separate; this family is sentiment context only and cannot veto DEPLOY.",
    }


def append_history(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(row)
    rows: list[dict] = []
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            fields = list(reader.fieldnames or [])
        for key in row:
            if key not in fields:
                fields.append(key)
        if rows and rows[-1].get("timestamp_et") == row.get("timestamp_et"):
            rows[-1] = row
        else:
            rows.append(row)
    else:
        rows = [row]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--history", required=True)
    args = parser.parse_args()
    snapshot_path, history_path = Path(args.snapshot), Path(args.history)
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    values = payload.get("values") or {}
    unified = payload.get("unified_engine") or {}
    market_date = unified.get("market_date") or values.get("market_date")
    stamp = unified.get("timestamp_et") or values.get("timestamp_et") or datetime.now(ET).isoformat()

    families = {}
    errors = {}
    builders = {
        "vol_structure": vix_term_structure,
        "breadth_thrust": lambda: breadth_thrust(values),
        "risk_appetite": risk_appetite,
        "options_sentiment": lambda: cboe_put_call(str(market_date)),
    }
    for key, builder in builders.items():
        try:
            families[key] = builder()
        except Exception as exc:
            errors[key] = f"{type(exc).__name__}: {exc}"
            families[key] = {"name": key.replace("_", " ").title(), "state": "UNAVAILABLE", "supportive": False,
                             "retail_explanation": "This signal could not be calculated from the current data feed.",
                             "validation_status": "RESEARCH_PENDING", "error": errors[key]}

    research_support = sum(bool(v.get("supportive")) for v in families.values())
    overlay = {
        "version": "REENTRY_SECONDARY_CONFIRMATION_v1",
        "timestamp_et": stamp,
        "market_date": market_date,
        "decision_input": False,
        "changes_deploy_trigger": False,
        "changes_recovery_stage": False,
        "supportive_family_count": research_support,
        "family_count": len(families),
        "families": families,
        "errors": errors,
        "interpretation": "Secondary confirmation describes whether participation, volatility structure, risk appetite, and options sentiment are corroborating the existing RE-ENTRY signal. It does not create, block, delay, or revoke DEPLOY.",
    }
    payload["secondary_confirmation"] = overlay
    if unified:
        unified["secondary_confirmation"] = overlay
        payload["unified_engine"] = unified
    snapshot_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    row = {
        "market_date": market_date,
        "timestamp_et": stamp,
        "deployment_signal": unified.get("deployment_signal"),
        "market_condition": unified.get("market_condition"),
        "recovery_stage": unified.get("recovery_stage"),
        "supportive_family_count": research_support,
    }
    for key, family in families.items():
        row[f"{key}_state"] = family.get("state")
        row[f"{key}_supportive"] = family.get("supportive")
    append_history(history_path, row)
    print(json.dumps(overlay, indent=2))


if __name__ == "__main__":
    main()
