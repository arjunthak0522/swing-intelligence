from __future__ import annotations

import json
import re
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

from reentry_cash_policy_validation import historical_proxy_states, forward_return
from reentry_confidence import feature_frame
from reentry_walkforward_validation import generate_decisions
from reentry_secondary_confirmation import ticker_close

OUTDIR = Path("artifacts/reentry_secondary_family_validation")
HORIZONS = (5, 10, 15, 30, 60, 90)
ROUND_TRIP_COST = 0.001
CBOE_EQUITY_ARCHIVE = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/equitypc.csv"
CBOE_INDEX_ARCHIVE = "https://cdn.cboe.com/resources/options/volume_and_call_put_ratios/indexpc.csv"
CBOE_DAILY = "https://www.cboe.com/markets/us/options/market-statistics/daily?dt={date}"
UNICORN_ROOT = "https://unicorn.us.com/advdec/"
HEADERS = {"User-Agent": "Mozilla/5.0 RE-ENTRY validation/1.0"}


def summarize(x: pd.Series) -> dict:
    x = pd.to_numeric(x, errors="coerce").dropna()
    if x.empty:
        return {"n": 0, "median": None, "mean": None, "positive_rate": None}
    return {
        "n": int(len(x)),
        "median": float(x.median()),
        "mean": float(x.mean()),
        "positive_rate": float((x > 0).mean()),
    }


def episode_starts(signal: pd.Series) -> pd.Series:
    s = signal.fillna(False).astype(bool)
    return s & ~s.shift(1, fill_value=False)


def normalize_index(s: pd.Series) -> pd.Series:
    s = s.copy()
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx.normalize()
    return s[~s.index.duplicated(keep="last")].sort_index()


def conditional_forward(states: pd.DataFrame, frame: pd.DataFrame, mask: pd.Series) -> dict:
    out = {"episodes": int(mask.sum()), "SPY": {}, "QQQ": {}}
    for sym in ("SPY", "QQQ"):
        px = frame[sym].reindex(states.index)
        for h in HORIZONS:
            out[sym][str(h)] = summarize(forward_return(px, h).loc[mask])
    return out


def forward_delta(base: dict, subset: dict) -> dict:
    out = {"SPY": {}, "QQQ": {}}
    for sym in ("SPY", "QQQ"):
        for h in HORIZONS:
            a, b = subset[sym][str(h)], base[sym][str(h)]
            out[sym][str(h)] = {
                "n": a["n"],
                "median_return_delta": None if a["median"] is None or b["median"] is None else float(a["median"] - b["median"]),
                "positive_rate_delta": None if a["positive_rate"] is None or b["positive_rate"] is None else float(a["positive_rate"] - b["positive_rate"]),
            }
    return out


def waiting_cost(states: pd.DataFrame, frame: pd.DataFrame, starts: pd.Series, signal: pd.Series, max_wait: int = 5) -> dict:
    start_pos = np.flatnonzero(starts.to_numpy())
    signal = signal.reindex(states.index).fillna(False).astype(bool)
    rows = []
    for pos in start_pos:
        wait = None
        for k in range(0, max_wait + 1):
            j = pos + k
            if j >= len(states):
                break
            if bool(signal.iloc[j]):
                wait = k
                break
        rec = {"signal_pos": int(pos), "wait_sessions": wait}
        if wait is not None and pos + 1 + wait < len(states):
            for sym in ("SPY", "QQQ"):
                px = frame[sym].reindex(states.index)
                immediate = float(px.iloc[pos + 1])
                delayed = float(px.iloc[pos + 1 + wait])
                rec[f"{sym}_entry_cost_of_waiting"] = delayed / immediate - 1.0
        rows.append(rec)
    r = pd.DataFrame(rows)
    confirmed = r[r["wait_sessions"].notna()].copy() if not r.empty else r
    return {
        "deploy_episode_count": int(len(rows)),
        "confirmed_within_window": int(len(confirmed)),
        "confirmation_rate": float(len(confirmed) / len(rows)) if rows else None,
        "median_wait_sessions": float(confirmed["wait_sessions"].median()) if len(confirmed) else None,
        "SPY_entry_cost_of_waiting": summarize(confirmed.get("SPY_entry_cost_of_waiting", pd.Series(dtype=float))),
        "QQQ_entry_cost_of_waiting": summarize(confirmed.get("QQQ_entry_cost_of_waiting", pd.Series(dtype=float))),
        "interpretation": "Positive entry_cost_of_waiting means requiring this confirmation bought later at a higher price than the original RE-ENTRY entry.",
    }


def quality_gate(base: dict, subset: dict, wait: dict, min_n: int = 25, allow_wait: bool = True) -> dict:
    checks = {}
    for sym in ("SPY", "QQQ"):
        for h in (10, 30):
            a, b = subset[sym][str(h)], base[sym][str(h)]
            checks[f"{sym}_{h}D_median_not_worse"] = bool(
                a["n"] >= min_n and a["median"] is not None and b["median"] is not None and a["median"] >= b["median"]
            )
            checks[f"{sym}_{h}D_hit_rate_not_damaged"] = bool(
                a["n"] >= min_n and a["positive_rate"] is not None and b["positive_rate"] is not None
                and a["positive_rate"] >= b["positive_rate"] - 0.03
            )
    quality = all(checks.values()) if checks else False
    timing = True
    if allow_wait:
        timing = bool(
            wait.get("median_wait_sessions") is not None
            and wait["median_wait_sessions"] <= 1.0
            and (wait["SPY_entry_cost_of_waiting"].get("median") or 0.0) <= 0.0025
            and (wait["QQQ_entry_cost_of_waiting"].get("median") or 0.0) <= 0.0025
        )
    return {"checks": checks, "quality_pass": quality, "timing_pass": timing}


def build_risk_appetite(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict]:
    tickers = ["RSP", "SPY", "IWM", "HYG", "LQD"]
    raw = yf.download(
        tickers,
        start=(index.min() - pd.Timedelta(days=15)).strftime("%Y-%m-%d"),
        end=(index.max() + pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
        timeout=30,
    )
    px = {}
    for t in tickers:
        s = ticker_close(raw, t)
        px[t] = normalize_index(s)
    out = pd.DataFrame(index=index)
    pairs = [("RSP", "SPY", "equal_weight"), ("IWM", "SPY", "small_caps"), ("HYG", "LQD", "credit")]
    for a, b, name in pairs:
        ratio = (px[a] / px[b]).dropna()
        out[f"{name}_5d"] = ratio.pct_change(5).reindex(index)
        out[f"{name}_supportive"] = out[f"{name}_5d"] > 0
    flags = [f"{name}_supportive" for _, _, name in pairs]
    out["supportive_components"] = out[flags].sum(axis=1)
    out["supportive"] = out["supportive_components"] >= 2
    return out, {
        "source": "Yahoo Finance adjusted daily closes",
        "definition": "RSP/SPY, IWM/SPY, and HYG/LQD positive 5-session relative momentum; >=2 of 3 = supportive",
        "coverage_start": str(out.dropna(how="all").index.min().date()),
        "coverage_end": str(out.dropna(how="all").index.max().date()),
    }


def parse_unicorn_series(text: str) -> pd.Series:
    df = pd.read_csv(StringIO(text), header=None, comment="#")
    if df.shape[1] < 2:
        raise RuntimeError("Unexpected Unicorn CSV schema")
    dates = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    vals = pd.to_numeric(df.iloc[:, 1], errors="coerce")
    s = pd.Series(vals.values, index=dates).dropna()
    s = s[~s.index.isna()]
    return normalize_index(s)


def build_breadth_thrust(index: pd.DatetimeIndex) -> tuple[pd.DataFrame, dict]:
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    page = requests.get(UNICORN_ROOT, headers=HEADERS, timeout=30, verify=False)
    page.raise_for_status()
    soup = BeautifulSoup(page.text, "html.parser")
    links = None
    for tr in soup.find_all("tr"):
        text = " ".join(tr.stripped_strings).upper()
        if text.startswith("NASDAQ"):
            csvs = [urljoin(UNICORN_ROOT, a.get("href")) for a in tr.find_all("a") if a.get("href") and ".csv" in a.get("href").lower()]
            if len(csvs) >= 2:
                links = csvs
                break
    if not links:
        raise RuntimeError("Could not locate NASDAQ advancer/decliner CSV links on Unicorn history page")
    adv_text = requests.get(links[0], headers=HEADERS, timeout=30, verify=False).text
    dec_text = requests.get(links[1], headers=HEADERS, timeout=30, verify=False).text
    adv, dec = parse_unicorn_series(adv_text), parse_unicorn_series(dec_text)
    common = adv.index.intersection(dec.index)
    share = (adv.reindex(common) / (adv.reindex(common) + dec.reindex(common))).replace([np.inf, -np.inf], np.nan)
    out = pd.DataFrame(index=index)
    out["advance_share"] = share.reindex(index)
    out["building"] = out["advance_share"] >= 0.55
    out["thrust_level"] = out["advance_share"] >= 0.615
    return out, {
        "source": "Unicorn Research historical NASDAQ advancing/declining issues (public history stops in February 2020)",
        "advancers_url": links[0],
        "decliners_url": links[1],
        "definition": "advance share = advancers / (advancers + decliners); >=55% building, >=61.5% thrust-level",
        "coverage_start": str(share.index.min().date()),
        "coverage_end": str(share.index.max().date()),
        "hard_limit": "The free exact advance/decline source ends in February 2020. This can falsify the family on the overlapping early window but cannot certify the 2020-2026 regime.",
    }


def parse_archive_ratio(url: str) -> pd.Series:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    date_col = next((c for c in df.columns if "date" in c.lower()), df.columns[0])
    ratio_cols = [c for c in df.columns if ("p/c" in c.lower() or "put/call" in c.lower() or "ratio" in c.lower())]
    if not ratio_cols:
        numeric = [c for c in df.columns if c != date_col]
        ratio_col = numeric[-1]
    else:
        ratio_col = ratio_cols[-1]
    dates = pd.to_datetime(df[date_col], errors="coerce")
    vals = pd.to_numeric(df[ratio_col], errors="coerce")
    s = pd.Series(vals.values, index=dates).dropna()
    s = s[~s.index.isna()]
    return normalize_index(s)


def fetch_cboe_daily(date: pd.Timestamp) -> tuple[pd.Timestamp, float | None, float | None]:
    ds = pd.Timestamp(date).strftime("%Y-%m-%d")
    for _ in range(2):
        try:
            r = requests.get(CBOE_DAILY.format(date=ds), headers=HEADERS, timeout=20)
            r.raise_for_status()
            text = " ".join(BeautifulSoup(r.text, "html.parser").stripped_strings)
            def val(label: str):
                m = re.search(re.escape(label) + r"\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
                return float(m.group(1)) if m else None
            return pd.Timestamp(date).normalize(), val("EQUITY PUT/CALL RATIO"), val("INDEX PUT/CALL RATIO")
        except Exception:
            continue
    return pd.Timestamp(date).normalize(), None, None


def build_options_sentiment(index: pd.DatetimeIndex, starts: pd.Series) -> tuple[pd.DataFrame, dict]:
    equity = parse_archive_ratio(CBOE_EQUITY_ARCHIVE)
    index_pc = parse_archive_ratio(CBOE_INDEX_ARCHIVE)
    archive_end = min(equity.index.max(), index_pc.index.max())
    positions = np.flatnonzero(starts.to_numpy())
    needed = set()
    for pos in positions:
        for k in range(-1, 4):
            j = pos + k
            if 0 <= j < len(index):
                d = pd.Timestamp(index[j]).normalize()
                if d > archive_end:
                    needed.add(d)
    fetched = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = [ex.submit(fetch_cboe_daily, d) for d in sorted(needed)]
        for fut in as_completed(futs):
            fetched.append(fut.result())
    for d, eq, ix in fetched:
        if eq is not None:
            equity.loc[d] = eq
        if ix is not None:
            index_pc.loc[d] = ix
    equity, index_pc = equity.sort_index(), index_pc.sort_index()
    out = pd.DataFrame(index=index)
    out["equity_pc"] = equity.reindex(index)
    out["index_pc"] = index_pc.reindex(index)
    out["equity_fear"] = out["equity_pc"] >= 0.70
    out["equity_high_fear"] = out["equity_pc"] >= 0.90
    out["equity_change1"] = out["equity_pc"].diff()
    out["index_change1"] = out["index_pc"].diff()
    out["fear_reversing"] = (out["equity_pc"].shift(1) >= 0.70) & (out["equity_change1"] <= -0.05)
    out["fear_reversing_broad"] = out["fear_reversing"] & (out["index_change1"] < 0)
    fetched_valid = sum(1 for _, eq, ix in fetched if eq is not None or ix is not None)
    return out, {
        "source": "Cboe equity/index put-call archive through 2019-10-04 plus Cboe Daily Market Statistics on required later episode-window dates",
        "archive_end": str(archive_end.date()),
        "requested_post_archive_dates": len(needed),
        "valid_post_archive_dates": fetched_valid,
        "equity_fear_definition": "equity put/call >=0.70",
        "high_fear_definition": "equity put/call >=0.90",
        "reversal_definition": "prior equity put/call >=0.70 and current falls by at least 0.05; broad reversal also requires index put/call to fall",
        "structural_break": "Cboe has documented that large early-exercise order flow distorted raw equity put/call readings in 2022; post-2022 raw ratios therefore receive an explicit stability penalty in the promotion decision.",
    }


def evaluate_family(name: str, states: pd.DataFrame, frame: pd.DataFrame, starts: pd.Series, signal: pd.Series, min_n: int = 25, max_wait: int = 5) -> dict:
    signal = signal.reindex(states.index).fillna(False).astype(bool)
    base = conditional_forward(states, frame, starts)
    subset = conditional_forward(states, frame, starts & signal)
    wait = waiting_cost(states, frame, starts, signal, max_wait=max_wait)
    gate = quality_gate(base, subset, wait, min_n=min_n)
    return {
        "name": name,
        "base": base,
        "supportive_subset": subset,
        "incremental_vs_all_deploy": forward_delta(base, subset),
        "waiting_cost": wait,
        "gate": gate,
    }


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    frame, metadata = feature_frame(return_metadata=True, require_same_day=False)
    decisions = generate_decisions(frame)
    states = historical_proxy_states(frame, decisions)
    frame = frame.reindex(states.index)
    idx = pd.DatetimeIndex(states.index).tz_localize(None).normalize()
    states.index = idx
    frame.index = idx
    starts = episode_starts(states["deployment_signal"].eq("DEPLOY"))

    risk, risk_meta = build_risk_appetite(idx)
    risk_eval = evaluate_family("risk_appetite_broadening", states, frame, starts, risk["supportive"], min_n=25, max_wait=5)
    risk_corr = pd.to_numeric(risk["supportive_components"], errors="coerce").corr(pd.to_numeric(states["B50"], errors="coerce"))
    risk_quality = risk_eval["gate"]["quality_pass"]
    risk_timing = risk_eval["gate"]["timing_pass"]
    risk_verdict = "PROMOTE_TO_RECOVERY_CONFIRMATION" if risk_quality and risk_timing and (pd.isna(risk_corr) or abs(risk_corr) < 0.75) else "KEEP_SECONDARY_CONTEXT"
    risk_eval["redundancy"] = {"corr_supportive_count_with_B50": None if pd.isna(risk_corr) else float(risk_corr)}
    risk_eval["verdict"] = {
        "verdict": risk_verdict,
        "decision_logic_change_authorized": False,
        "recovery_stage_change_authorized": risk_verdict == "PROMOTE_TO_RECOVERY_CONFIRMATION",
    }

    breadth_error = None
    try:
        breadth, breadth_meta = build_breadth_thrust(idx)
        available_starts = starts & breadth["advance_share"].notna()
        breadth_eval = evaluate_family("breadth_participation_thrust", states, frame, available_starts, breadth["building"], min_n=12, max_wait=5)
        thrust_eval = conditional_forward(states, frame, available_starts & breadth["thrust_level"].fillna(False))
        n_available = int(available_starts.sum())
        quality = breadth_eval["gate"]["quality_pass"]
        if n_available < 20:
            breadth_verdict = "KEEP_RESEARCH_ONLY_LIMITED_EXACT_HISTORY"
        elif quality:
            breadth_verdict = "PROMOTE_TO_RECOVERY_CONFIRMATION_CANDIDATE_LIMITED_WINDOW"
        else:
            breadth_verdict = "KEEP_SECONDARY_CONTEXT_NO_INCREMENTAL_EDGE"
        breadth_eval["thrust_level_subset"] = thrust_eval
        breadth_eval["available_deploy_episodes"] = n_available
        breadth_eval["verdict"] = {
            "verdict": breadth_verdict,
            "decision_logic_change_authorized": False,
            "recovery_stage_change_authorized": False,
            "hard_limit": breadth_meta["hard_limit"],
        }
    except Exception as exc:
        breadth_error = f"{type(exc).__name__}: {exc}"
        breadth_meta = {"error": breadth_error}
        breadth_eval = {
            "name": "breadth_participation_thrust",
            "verdict": {
                "verdict": "KEEP_RESEARCH_ONLY_DATA_SOURCE_FAILURE",
                "decision_logic_change_authorized": False,
                "recovery_stage_change_authorized": False,
            },
        }

    options, options_meta = build_options_sentiment(idx, starts)
    options_tests = {}
    for label, sig in {
        "EQUITY_FEAR": options["equity_fear"],
        "EQUITY_HIGH_FEAR": options["equity_high_fear"],
        "FEAR_REVERSING": options["fear_reversing"],
        "FEAR_REVERSING_BROAD": options["fear_reversing_broad"],
    }.items():
        options_tests[label] = evaluate_family(label.lower(), states, frame, starts, sig, min_n=15, max_wait=3)
    post2022 = starts & (pd.Series(idx, index=idx) >= pd.Timestamp("2022-01-01"))
    pre2022 = starts & (pd.Series(idx, index=idx) < pd.Timestamp("2022-01-01"))
    segment = {}
    for seg_name, seg_mask in {"PRE_2022": pre2022, "POST_2022": post2022}.items():
        segment[seg_name] = {
            "base": conditional_forward(states, frame, seg_mask),
            "equity_fear": conditional_forward(states, frame, seg_mask & options["equity_fear"].fillna(False)),
            "fear_reversing": conditional_forward(states, frame, seg_mask & options["fear_reversing"].fillna(False)),
        }

    reversal = options_tests["FEAR_REVERSING"]
    reversal_n = reversal["supportive_subset"]["episodes"]
    reversal_quality = reversal["gate"]["quality_pass"]
    post_fear_n = segment["POST_2022"]["equity_fear"]["episodes"]
    if reversal_quality and reversal_n >= 15:
        options_verdict = "KEEP_SENTIMENT_OVERLAY_VALIDATED_REVERSAL_SUPPORT"
    else:
        options_verdict = "KEEP_SENTIMENT_OVERLAY_NO_PROMOTION"
    options_result = {
        "tests": options_tests,
        "regime_segments": segment,
        "verdict": {
            "verdict": options_verdict,
            "decision_logic_change_authorized": False,
            "recovery_stage_change_authorized": False,
            "structural_break_penalty": True,
            "post_2022_fear_episode_count": int(post_fear_n),
            "note": options_meta["structural_break"],
        },
    }

    payload = {
        "status": "COMPLETE",
        "question": "Do breadth thrust, risk-appetite broadening, and options sentiment add incremental information after RE-ENTRY already says DEPLOY, without making the proven early-entry behavior materially later?",
        "date_range": [str(idx.min().date()), str(idx.max().date())],
        "deploy_episode_count": int(starts.sum()),
        "methodology": {
            "entry": "signal known at close t; hypothetical entry close t+1",
            "horizons": list(HORIZONS),
            "round_trip_cost": ROUND_TRIP_COST,
            "episode_sampling": "first session of each contiguous historical proxy DEPLOY episode",
            "no_change_to_live_engine": True,
            "promotion_scope": "At most recovery-confirmation or context. No test in this batch can alter the DEPLOY trigger automatically.",
        },
        "data_metadata": metadata,
        "risk_appetite": {"metadata": risk_meta, "result": risk_eval},
        "breadth_thrust": {"metadata": breadth_meta, "result": breadth_eval, "error": breadth_error},
        "options_sentiment": {"metadata": options_meta, "result": options_result},
        "overall": {
            "deploy_trigger_change_authorized": False,
            "family_verdicts": {
                "breadth_thrust": breadth_eval["verdict"]["verdict"],
                "risk_appetite": risk_eval["verdict"]["verdict"],
                "options_sentiment": options_result["verdict"]["verdict"],
            },
        },
    }
    (OUTDIR / "secondary_family_incremental_validation.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    risk.to_csv(OUTDIR / "risk_appetite_history.csv", index_label="date")
    options.to_csv(OUTDIR / "options_sentiment_episode_window_history.csv", index_label="date")
    if breadth_error is None:
        breadth.to_csv(OUTDIR / "breadth_thrust_history_limited.csv", index_label="date")

    print(json.dumps(payload["overall"], indent=2))
    print(json.dumps({
        "risk_appetite": risk_eval["verdict"],
        "breadth_thrust": breadth_eval["verdict"],
        "options_sentiment": options_result["verdict"],
    }, indent=2))


if __name__ == "__main__":
    main()
