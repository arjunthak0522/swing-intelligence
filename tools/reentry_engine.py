from __future__ import annotations

from datetime import time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import reentry_confidence as confidence
from reentry_confidence import analogs_for_date, empirical_state, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
from reentry_evidence import EVIDENCE_HORIZONS, summarize_extended_evidence

ENGINE_VERSION = "reentry_v1.0"
SCHEMA_VERSION = "1.0"
ANALOG_DECISIONS = {"NO", "CAUTIOUS YES", "YES", "STRONG YES"}
STRATEGY_SIGNALS = {"RE-ENTER", "WAIT", "NO RE-ENTRY SETUP"}
LIVE_CLOSE_BUFFER_ET = time(16, 15)
_BASE_FETCH_TWELVE_CLOSE = confidence.fetch_twelve_close


def weakness_context(row) -> tuple[bool, list[str]]:
    """Frozen V1 weakness context. Do not tune without a new engine version."""
    reasons: list[str] = []
    if float(row["spy_dd20"]) <= -0.01:
        reasons.append("SPY is at least 1% below its 20-day high")
    if float(row["B50"]) <= 0.50:
        reasons.append("50% or fewer S&P 500 stocks are above their 50DMA")
    if float(row["vix_change5"]) >= 0.10:
        reasons.append("VIX is up at least 10% over 5 trading days")
    if float(row["curve_ratio"]) >= 1.0:
        reasons.append("VIX/VIX3M is at or above 1.0")
    return bool(reasons), reasons


def strategy_signal(decision: str, weak: bool) -> tuple[str, str]:
    """Frozen V1 operational mapping from weakness + analog decision to action state."""
    if weak and decision in {"CAUTIOUS YES", "YES", "STRONG YES"}:
        return "RE-ENTER", "meaningful weakness is present and historical analogs do not support continuing to wait"
    if weak:
        return "WAIT", "weakness is present, but historical analogs do not yet support re-entry"
    return "NO RE-ENTRY SETUP", "no qualifying weakness is currently present"


def fetch_completed_twelve_close(symbol: str, start: str = "2016-09-01") -> pd.Series:
    """Fetch daily prices while refusing to treat today's live daily bar as a completed close."""
    series = _BASE_FETCH_TWELVE_CLOSE(symbol, start=start)
    now_et = pd.Timestamp.now(tz=ZoneInfo("America/New_York"))
    today = pd.Timestamp(now_et.date())
    if now_et.weekday() < 5 and now_et.time() < LIVE_CLOSE_BUFFER_ET and today in series.index:
        series = series.drop(index=today)
    if series.empty:
        raise RuntimeError(f"No completed daily closes available for {symbol}")
    return series


def _single_yahoo_close(ticker: str, target: pd.Timestamp) -> float | None:
    """Return one completed Yahoo daily close, or None if that exact field is unavailable."""
    try:
        import yfinance as yf

        raw = yf.download(
            ticker,
            period="1mo",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
            group_by="column",
        )
        if raw.empty:
            return None
        raw = confidence._normalize_daily_index(raw)
        target = pd.Timestamp(target).normalize()
        if target not in raw.index:
            return None
        close = raw["Close"]
        if isinstance(close, pd.DataFrame):
            if close.shape[1] == 0:
                return None
            value = float(pd.to_numeric(close.iloc[:, 0], errors="coerce").loc[target])
        else:
            value = float(pd.to_numeric(close, errors="coerce").loc[target])
        if np.isfinite(value) and value > 0:
            return value
    except Exception:
        return None
    return None


def _robust_same_day_vol(target: pd.Timestamp) -> tuple[float, float]:
    """Resolve VIX and VIX3M independently so an unused bad fallback cannot block live mode."""
    target = pd.Timestamp(target).normalize()
    values: dict[str, float] = {}
    for symbol, ticker in (("VIX", "^VIX"), ("VIX3M", "^VIX3M")):
        yahoo = _single_yahoo_close(ticker, target)
        if yahoo is not None:
            values[symbol] = yahoo
            continue
        historical, _ = confidence.fetch_volatility_history(symbol)
        historical = confidence._normalize_daily_index(historical)
        if target in historical.index:
            value = float(historical.loc[target])
            if np.isfinite(value) and value > 0:
                values[symbol] = value
                continue
        raise RuntimeError(f"No valid completed {symbol} close for {target.date()}")
    return values["VIX"], values["VIX3M"]


def _install_live_data_hardening() -> None:
    # Data plumbing only. This does not alter features, thresholds, analog selection, or decisions.
    confidence.fetch_twelve_close = fetch_completed_twelve_close
    confidence.fetch_yahoo_same_day_vol = _robust_same_day_vol


def _analog_rows(analogs) -> list[dict[str, Any]]:
    return [
        {"rank": rank, "date": str(date.date()), "distance": float(row["distance"])}
        for rank, (date, row) in enumerate(analogs.iterrows(), start=1)
    ]


def historical_validation_block() -> dict[str, Any]:
    return {
        "independent_episodes": 145,
        "SPY_7D_median_after_signal": 0.008585570190091318,
        "SPY_10D_median_after_signal": 0.010660180393483043,
        "QQQ_7D_median_after_signal": 0.010538951553654141,
        "QQQ_10D_median_after_signal": 0.014405462638181654,
        "SPY_7D_positive_rate": 0.6551724137931034,
        "SPY_10D_positive_rate": 0.6689655172413793,
        "QQQ_7D_positive_rate": 0.6137931034482759,
        "QQQ_10D_positive_rate": 0.6344827586206897,
        "result": "GO_TO_IMPLEMENTABLE_STRATEGY",
        "important_limit": (
            "the model did not prove superiority to entering immediately at the start of every weakness episode; "
            "it did show that, once its re-entry condition was present, waiting another 3-5 sessions was historically worse"
        ),
    }


def build_snapshot(require_same_day: bool = True) -> dict[str, Any]:
    """Build the one authoritative daily engine object consumed by persistence and UI."""
    if require_same_day:
        _install_live_data_hardening()
    frame, freshness = feature_frame(return_metadata=True, require_same_day=require_same_day)
    target = frame.index.max()
    row = frame.loc[target]
    analogs = analogs_for_date(frame, target)
    decision_stats = summarize_analogs(frame, analogs)
    extended_evidence = summarize_extended_evidence(frame, analogs)
    decision, interpretation, diagnostics = decision_from_analogs(decision_stats, row)
    weak, weak_reasons = weakness_context(row)
    signal, signal_text = strategy_signal(decision, weak)

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "as_of": str(target.date()),
        "strategy": "Correction Re-entry",
        "question": "Does it make sense to put cash back into the market right now?",
        "data_freshness": freshness,
        "signal": signal,
        "signal_interpretation": signal_text,
        "analog_decision": decision,
        "analog_interpretation": interpretation,
        "market_state": empirical_state(row),
        "weakness_present": weak,
        "weakness_reasons": weak_reasons,
        "current_inputs": {
            "spy_drawdown_20d": float(row["spy_dd20"]),
            "spy_return_5d": float(row["spy_ret5"]),
            "pct_sp500_above_50dma": float(row["B50"]),
            "pct_sp500_above_200dma": float(row["B200"]),
            "breadth_1d_change": float(row["b50_change1"]),
            "breadth_3d_change": float(row["b50_change3"]),
            "vix_5d_change": float(row["vix_change5"]),
            "vix_vix3m_ratio": float(row["curve_ratio"]),
        },
        "analog_count": int(len(analogs)),
        "analogs": _analog_rows(analogs),
        "forward_analog_outcomes": decision_stats,
        "extended_forward_evidence": extended_evidence,
        "evidence_horizons": list(EVIDENCE_HORIZONS),
        "drawdown_definition": "close-to-close maximum adverse excursion from hypothetical close t+1 entry through each horizon",
        "decision_diagnostics": diagnostics,
        "implementation": {
            "evaluate": "after each market close",
            "freshness_policy": "SPY/QQQ are filtered to the latest completed U.S. equity session; today's live daily bar is discarded before 4:15 PM ET; VIX, VIX3M, and breadth must match that completed session or no signal is emitted",
            "weakness_context": "SPY >=1% below 20d high OR <=50% S&P above 50DMA OR VIX +>=10% over 5d OR VIX/VIX3M >=1.0",
            "reentry_rule": "when weakness exists and analog decision is CAUTIOUS YES / YES / STRONG YES, signal RE-ENTER",
            "decision_basis": "40 nearest prior market-state analogs; operational decision remains based on frozen 7D/10D SPY/QQQ cells",
            "execution": "actionable for the next trading session; historical validation assumed close t+1 execution and 10 bps round-trip friction",
            "exit_rule": "none; this is an entry-timing framework for redeploying cash, not a forced short-horizon swing exit",
            "forward_evidence": "always report 5/7/10/15/30/60D return, positive rate, and drawdown-path statistics",
            "large_corrections": "fully included; there is no maximum drawdown exclusion",
            "rolling_corrections": "included through breadth and volatility weakness even when the index drawdown is shallow",
        },
        "historical_validation": historical_validation_block(),
        "caveats": [
            "true breadth history begins in September 2016",
            "historical evidence supports decision timing, not guaranteed returns",
            "drawdown statistics are based on daily closes, not intraday lows",
            "this does not claim statistically proven standalone alpha versus buy-and-hold",
        ],
    }
    validate_snapshot(snapshot, require_same_day=require_same_day)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any], require_same_day: bool = True) -> None:
    required = {
        "schema_version", "engine_version", "as_of", "signal", "analog_decision",
        "market_state", "current_inputs", "analogs", "extended_forward_evidence",
        "evidence_horizons", "data_freshness",
    }
    missing = sorted(required - snapshot.keys())
    if missing:
        raise ValueError(f"Snapshot missing required fields: {missing}")
    if snapshot["engine_version"] != ENGINE_VERSION:
        raise ValueError(f"Unexpected engine version: {snapshot['engine_version']}")
    if snapshot["signal"] not in STRATEGY_SIGNALS:
        raise ValueError(f"Invalid strategy signal: {snapshot['signal']}")
    if snapshot["analog_decision"] not in ANALOG_DECISIONS:
        raise ValueError(f"Invalid analog decision: {snapshot['analog_decision']}")
    if list(snapshot["evidence_horizons"]) != list(EVIDENCE_HORIZONS):
        raise ValueError("Evidence horizons do not match frozen engine contract")
    if len(snapshot["analogs"]) != 40:
        raise ValueError(f"Expected 40 analogs, found {len(snapshot['analogs'])}")
    if require_same_day and not snapshot["data_freshness"].get("same_day_complete", False):
        raise ValueError("Live snapshot is not same-day complete")
    for symbol in ("SPY", "QQQ"):
        evidence = snapshot["extended_forward_evidence"].get(symbol, {})
        for horizon in EVIDENCE_HORIZONS:
            cell = evidence.get(str(horizon))
            if not cell or int(cell.get("n", 0)) <= 0:
                raise ValueError(f"Missing {symbol} {horizon}D evidence")
            for field in ("median_return", "positive_rate", "median_max_drawdown", "p10_max_drawdown", "worst_max_drawdown"):
                if field not in cell:
                    raise ValueError(f"Missing {symbol} {horizon}D field {field}")
