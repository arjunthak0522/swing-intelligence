#!/usr/bin/env python3
"""Research-only validation of candidate intraday context signals around RE-ENTRY episodes.

This does NOT modify the frozen RE-ENTRY engine. It uses recent 5-minute Yahoo chart data
and the reconstructed episode ledger to test whether simple intraday features add useful
context after a RE-ENTRY signal. Output is descriptive and explicitly non-canonical.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "web/public/reentry/validation/historical_episode_ledger_2026-09-09.json"
OUT_JSON = ROOT / "research/intraday_signal_validation.json"
OUT_MD = ROOT / "research/intraday_signal_validation.md"

GROUPS = {
    "broad": ["SPY", "QQQ"],
    "sectors": ["XLC", "XLY", "XLP", "XLE", "XLF", "XLV", "XLI", "XLB", "XLRE", "XLK", "XLU"],
    "factors": ["MTUM", "QUAL", "VLUE", "IWF", "IWD", "USMV", "SPYD", "IWM"],
    "subsectors": [
        "FDN", "IYZ", "PBS", "XRT", "ITB", "PEJ", "PBJ", "RHS", "XOP", "OIH", "CRAK",
        "KRE", "KBE", "IAI", "KIE", "XBI", "IBB", "IHI", "IHF", "ITA", "XTN", "PAVE",
        "XME", "COPX", "SLX", "REZ", "SRVR", "NETL", "SMH", "IGV", "HACK", "RNRG", "RYU",
    ],
    "volatility": ["^VIX", "^VIX3M"],
}
ALL = list(dict.fromkeys(sum(GROUPS.values(), [])))
SNAPSHOTS = ["10:30", "12:00", "13:30", "15:00"]


def safe_mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]
    return sum(xs) / len(xs) if xs else None


def safe_median(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]
    return statistics.median(xs) if xs else None


def positive_share(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and math.isfinite(x)]
    return sum(x > 0 for x in xs) / len(xs) if xs else None


def yahoo_chart(symbol: str, interval: str, range_: str):
    q = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?interval={interval}&range={range_}&includePrePost=false&events=div%2Csplits"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 RE-ENTRY-research/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        body = json.loads(r.read().decode("utf-8"))
    result = body.get("chart", {}).get("result", [None])[0]
    if not result:
        raise RuntimeError(f"{symbol}: missing chart result")
    ts = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    rows = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if not isinstance(c, (int, float)) or not math.isfinite(c):
            continue
        rows.append({
            "ts": int(t), "close": float(c),
            "open": float(opens[i]) if i < len(opens) and isinstance(opens[i], (int, float)) else None,
            "high": float(highs[i]) if i < len(highs) and isinstance(highs[i], (int, float)) else None,
            "low": float(lows[i]) if i < len(lows) and isinstance(lows[i], (int, float)) else None,
        })
    return rows


def download_intraday():
    out, errors = {}, []
    for i, s in enumerate(ALL):
        try:
            out[s] = yahoo_chart(s, "5m", "60d")
        except Exception as e:
            errors.append(f"{s}: {e}")
        if i % 10 == 9:
            time.sleep(0.6)
    return out, errors


def daily_closes(symbol: str):
    rows = yahoo_chart(symbol, "1d", "6mo")
    out = {}
    for r in rows:
        d = datetime.fromtimestamp(r["ts"], timezone.utc).astimezone(ET).date().isoformat()
        out[d] = r["close"]
    return out


def group_by_date(rows):
    out = {}
    for r in rows:
        dt = datetime.fromtimestamp(r["ts"], timezone.utc).astimezone(ET)
        d = dt.date().isoformat()
        if dt.hour < 9 or (dt.hour == 9 and dt.minute < 30) or dt.hour >= 16:
            continue
        out.setdefault(d, []).append({**r, "dt": dt})
    for rows_ in out.values():
        rows_.sort(key=lambda x: x["ts"])
    return out


def bar_at(day_rows, hhmm):
    if not day_rows:
        return None
    h, m = map(int, hhmm.split(":"))
    candidates = [r for r in day_rows if (r["dt"].hour, r["dt"].minute) <= (h, m)]
    return candidates[-1] if candidates else None


def price_n_minutes_before(day_rows, bar, minutes=30):
    target = bar["ts"] - minutes * 60
    candidates = [r for r in day_rows if r["ts"] <= target]
    return candidates[-1]["close"] if candidates else None


def feature_for_symbol(day_rows, hhmm):
    bar = bar_at(day_rows, hhmm)
    if not bar:
        return None
    first = day_rows[0]
    prev30 = price_n_minutes_before(day_rows, bar, 30)
    highs = [r["high"] for r in day_rows if r["ts"] <= bar["ts"] and isinstance(r.get("high"), (int, float))]
    lows = [r["low"] for r in day_rows if r["ts"] <= bar["ts"] and isinstance(r.get("low"), (int, float))]
    open_px = first.get("open") or first["close"]
    high = max(highs) if highs else None
    low = min(lows) if lows else None
    return {
        "price": bar["close"],
        "from_open": bar["close"] / open_px - 1 if open_px else None,
        "last_30m": bar["close"] / prev30 - 1 if prev30 else None,
        "off_high": bar["close"] / high - 1 if high else None,
        "off_low": bar["close"] / low - 1 if low else None,
    }


def prior_daily_close(day_rows_by_date, date_):
    dates = sorted(d for d in day_rows_by_date if d < date_)
    if not dates:
        return None
    rows = day_rows_by_date[dates[-1]]
    return rows[-1]["close"] if rows else None


def snapshot_features(date_, hhmm, by_symbol_date):
    symbol = {}
    for s in ALL:
        days = by_symbol_date.get(s, {})
        f = feature_for_symbol(days.get(date_, []), hhmm)
        if f:
            prev = prior_daily_close(days, date_)
            f["vs_prev_close"] = f["price"] / prev - 1 if prev else None
            symbol[s] = f
    def moves(group, field="vs_prev_close"):
        return [symbol[s].get(field) for s in GROUPS[group] if s in symbol]
    broad_moves = moves("broad")
    sector_moves = moves("sectors")
    subsector_moves = moves("subsectors")
    factor_moves = moves("factors")
    vix = symbol.get("^VIX", {}).get("price")
    vix3m = symbol.get("^VIX3M", {}).get("price")
    vix_move = symbol.get("^VIX", {}).get("vs_prev_close")
    broad_30m = moves("broad", "last_30m")
    return {
        "symbol": symbol,
        "broad_mean": safe_mean(broad_moves),
        "both_indices_positive": len(broad_moves) == 2 and all(x > 0 for x in broad_moves),
        "sector_positive_share": positive_share(sector_moves),
        "subsector_positive_share": positive_share(subsector_moves),
        "factor_positive_share": positive_share(factor_moves),
        "sector_median_move": safe_median(sector_moves),
        "subsector_median_move": safe_median(subsector_moves),
        "factor_median_move": safe_median(factor_moves),
        "vix_change": vix_move,
        "vix_term_ratio": vix / vix3m if isinstance(vix, (int, float)) and isinstance(vix3m, (int, float)) and vix3m > 0 else None,
        "broad_last_30m": safe_mean(broad_30m),
        "quotes_available": len(symbol),
    }


def score_features(f, baseline_1030=None):
    checks = {
        "indices_confirm": bool(f.get("both_indices_positive")),
        "sectors_broad": (f.get("sector_positive_share") or -1) >= 0.55,
        "subsectors_broad": (f.get("subsector_positive_share") or -1) >= 0.55,
        "factors_broad": (f.get("factor_positive_share") or -1) >= 0.55,
        "vol_easing": isinstance(f.get("vix_change"), (int, float)) and f["vix_change"] < 0,
        "vol_curve_normal": isinstance(f.get("vix_term_ratio"), (int, float)) and f["vix_term_ratio"] < 1.0,
        "short_term_momentum": isinstance(f.get("broad_last_30m"), (int, float)) and f["broad_last_30m"] >= 0,
    }
    breadth_delta = None
    if baseline_1030:
        cur = safe_mean([f.get("sector_positive_share"), f.get("subsector_positive_share"), f.get("factor_positive_share")])
        base = safe_mean([baseline_1030.get("sector_positive_share"), baseline_1030.get("subsector_positive_share"), baseline_1030.get("factor_positive_share")])
        if cur is not None and base is not None:
            breadth_delta = cur - base
            checks["breadth_not_fading"] = breadth_delta >= 0
    score = sum(bool(v) for v in checks.values())
    return score, checks, breadth_delta


def next_returns(daily, date_, horizons=(1, 5, 10)):
    dates = sorted(daily)
    try:
        i = dates.index(date_)
    except ValueError:
        return {str(h): None for h in horizons}
    base = daily[date_]
    out = {}
    for h in horizons:
        j = i + h
        out[str(h)] = daily[dates[j]] / base - 1 if j < len(dates) else None
    return out


def metric_summary(rows, predicate, outcome_key):
    yes = [r[outcome_key] for r in rows if predicate(r) and isinstance(r.get(outcome_key), (int, float))]
    no = [r[outcome_key] for r in rows if not predicate(r) and isinstance(r.get(outcome_key), (int, float))]
    def s(xs):
        return {"n": len(xs), "mean": safe_mean(xs), "median": safe_median(xs), "positive_rate": positive_share(xs)}
    return {"present": s(yes), "absent": s(no)}


def fmt_pct(x):
    return "-" if x is None else f"{x*100:+.2f}%"


def main():
    ledger = json.loads(LEDGER.read_text())
    intraday, errors = download_intraday()
    by_symbol_date = {s: group_by_date(rows) for s, rows in intraday.items()}
    common_dates = sorted(set(by_symbol_date.get("SPY", {})) & set(by_symbol_date.get("QQQ", {})))
    if not common_dates:
        raise SystemExit("No usable SPY/QQQ intraday dates")
    first_date, last_date = common_dates[0], common_dates[-1]
    starts = sorted({e["start"] for e in ledger["episodes"] if first_date <= e["start"] <= last_date})
    spy_daily = daily_closes("SPY")
    qqq_daily = daily_closes("QQQ")

    observations = []
    for d in starts:
        base1030 = snapshot_features(d, "10:30", by_symbol_date)
        for t in SNAPSHOTS:
            f = snapshot_features(d, t, by_symbol_date)
            if f["quotes_available"] < 40:
                continue
            score, checks, breadth_delta = score_features(f, base1030 if t != "10:30" else None)
            spy_out = next_returns(spy_daily, d)
            qqq_out = next_returns(qqq_daily, d)
            row = {
                "date": d, "snapshot": t, "score": score, "checks": checks,
                "breadth_delta_since_1030": breadth_delta,
                "features": {k: v for k, v in f.items() if k != "symbol"},
            }
            for h in (1, 5, 10):
                row[f"SPY_{h}d"] = spy_out[str(h)]
                row[f"QQQ_{h}d"] = qqq_out[str(h)]
                vals = [x for x in (spy_out[str(h)], qqq_out[str(h)]) if isinstance(x, (int, float))]
                row[f"BROAD_{h}d"] = safe_mean(vals)
            observations.append(row)

    feature_keys = ["indices_confirm", "sectors_broad", "subsectors_broad", "factors_broad", "vol_easing", "vol_curve_normal", "short_term_momentum", "breadth_not_fading"]
    analysis = {}
    for t in SNAPSHOTS:
        rows = [r for r in observations if r["snapshot"] == t]
        by_feature = {}
        for key in feature_keys:
            by_feature[key] = {
                "5d": metric_summary(rows, lambda r, k=key: bool(r["checks"].get(k, False)), "BROAD_5d"),
                "10d": metric_summary(rows, lambda r, k=key: bool(r["checks"].get(k, False)), "BROAD_10d"),
            }
        analysis[t] = {
            "n_observations": len(rows),
            "score_6plus": {
                "5d": metric_summary(rows, lambda r: r["score"] >= 6, "BROAD_5d"),
                "10d": metric_summary(rows, lambda r: r["score"] >= 6, "BROAD_10d"),
            },
            "features": by_feature,
        }

    survivors = []
    for key in feature_keys:
        consistent_times = 0
        details = []
        for t in SNAPSHOTS:
            m5 = analysis[t]["features"][key]["5d"]
            m10 = analysis[t]["features"][key]["10d"]
            p5, a5 = m5["present"], m5["absent"]
            p10, a10 = m10["present"], m10["absent"]
            ok = p5["n"] >= 4 and a5["n"] >= 4 and p10["n"] >= 4 and a10["n"] >= 4 and (p5["mean"] or -9) > (a5["mean"] or -9) and (p10["mean"] or -9) > (a10["mean"] or -9)
            if ok:
                consistent_times += 1
            details.append({"snapshot": t, "directionally_better_5d_and_10d": ok})
        if consistent_times >= 2:
            survivors.append({"feature": key, "supporting_snapshots": consistent_times, "details": details})

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classification": "RESEARCH_ONLY_NON_CANONICAL",
        "engine_impact": "NONE",
        "data_source": "Yahoo Finance chart endpoint, 5-minute bars, recent 60-day availability",
        "sample_window": {"first_intraday_date": first_date, "last_intraday_date": last_date, "reentry_episode_starts": len(starts)},
        "limitations": [
            "Recent 5-minute vendor history is a small sample and is not point-in-time archived by this project.",
            "Episode dates come from the reconstructed ledger, not the archived independent-event validator.",
            "Candidate thresholds are predeclared research heuristics, not validated trading rules.",
            "Results are descriptive only; no intraday feature is promoted into the official completed-close RE-ENTRY engine by this script.",
        ],
        "download_errors": errors,
        "survivor_candidates": survivors,
        "analysis": analysis,
        "observations": observations,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True))

    lines = [
        "# RE-ENTRY intraday signal validation - research only",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "**No frozen RE-ENTRY signal logic is changed by this research.**",
        "",
        f"Recent 5-minute sample: **{first_date} through {last_date}**, covering **{len(starts)} reconstructed RE-ENTRY starts**.",
        "",
        "## Candidate features tested",
        "",
        "Index confirmation, sector breadth, subsector breadth, factor breadth, VIX direction, VIX/VIX3M term structure, 30-minute broad-index momentum, and breadth change since 10:30 ET.",
        "",
        "## Features that survived the initial directional screen",
        "",
    ]
    if survivors:
        for x in survivors:
            lines.append(f"- **{x['feature']}** - favorable subset had higher mean 5D and 10D broad-market forward return at {x['supporting_snapshots']} snapshot times with minimum sample checks.")
    else:
        lines.append("- **None.** The recent sample does not support promoting any tested intraday feature yet.")
    lines += ["", "## Snapshot diagnostics", ""]
    for t in SNAPSHOTS:
        a = analysis[t]
        lines.append(f"### {t} ET - n={a['n_observations']}")
        s5 = a["score_6plus"]["5d"]
        s10 = a["score_6plus"]["10d"]
        lines.append(f"- Score 6+ 5D: n={s5['present']['n']}, mean {fmt_pct(s5['present']['mean'])}; below 6: n={s5['absent']['n']}, mean {fmt_pct(s5['absent']['mean'])}")
        lines.append(f"- Score 6+ 10D: n={s10['present']['n']}, mean {fmt_pct(s10['present']['mean'])}; below 6: n={s10['absent']['n']}, mean {fmt_pct(s10['absent']['mean'])}")
        lines.append("")
    lines += [
        "## Decision rule for this research pass",
        "",
        "A feature is only called an initial survivor if the feature-present subset has a higher mean broad-market 5D **and** 10D return than the feature-absent subset at at least two snapshot times, with at least four observations in each side of the comparison.",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {x}" for x in payload["limitations"])
    OUT_MD.write_text("\n".join(lines) + "\n")
    print(json.dumps({"sample": payload["sample_window"], "survivors": survivors, "errors": errors}, indent=2))


if __name__ == "__main__":
    main()
