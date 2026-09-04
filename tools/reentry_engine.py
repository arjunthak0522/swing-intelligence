from __future__ import annotations

from datetime import time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import reentry_confidence as confidence
from internal_correction_full_v2 import build_full_v2_state
from internal_correction_v2 import FACTORS, SECTORS, build_cross_section, load_prices
from reentry_confidence import analogs_for_date, empirical_state, feature_frame, summarize_analogs
from reentry_decision import decision_from_analogs
from reentry_evidence import EVIDENCE_HORIZONS, summarize_extended_evidence

ENGINE_VERSION = "reentry_unified_research_1"
SCHEMA_VERSION = "2.0"
ANALOG_DECISIONS = {"NO", "CAUTIOUS YES", "YES", "STRONG YES"}
STRATEGY_SIGNALS = {"RE-ENTER", "WAIT", "NO RE-ENTRY SETUP"}
LIVE_CLOSE_BUFFER_ET = time(16, 15)
_BASE_FETCH_TWELVE_CLOSE = confidence.fetch_twelve_close
PROXY_CAVEAT = (
    "Sector and factor histories use liquid ETF proxies and are not proprietary "
    "point-in-time factor-index constituent histories."
)


def weakness_context(row) -> tuple[bool, list[str]]:
    """Validated broad-market weakness context retained inside the unified engine."""
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
    """Validated broad-market timing mapping retained for regression compatibility."""
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
        "result": "VALIDATED_BROAD_MARKET_TIMING_FOUNDATION",
        "important_limit": (
            "the model did not prove superiority to entering immediately at the start of every weakness episode; "
            "it did show that, once its re-entry condition was present, waiting another 3-5 sessions was historically worse"
        ),
    }


def _build_unified_frame(base: pd.DataFrame, require_same_day: bool) -> pd.DataFrame:
    prices = load_prices()
    xs = build_cross_section(prices)
    frame = base.join(xs, how="inner").dropna(subset=["spy_dd20", "sector_dispersion_pct"]).copy()
    if frame.empty:
        raise RuntimeError("Unified RE-ENTRY frame is empty")
    if require_same_day and frame.index.max() != base.index.max():
        raise RuntimeError(
            f"Same-day sector/factor data missing: market={base.index.max().date()} "
            f"cross_section={frame.index.max().date()}"
        )
    frame = build_full_v2_state(frame)
    return frame


def _internal_reset(row: pd.Series) -> str:
    if bool(row["v2_broad"]):
        return "BROAD"
    if bool(row["v2_meaningful"]):
        return "MEANINGFUL"
    if bool(row["v2_developing"]):
        return "DEVELOPING"
    return "NONE"


def _selling_pressure(row: pd.Series) -> str:
    repairing = (
        bool(row["v2_stabilizing"])
        and float(row["b50_change3"]) > 0
        and float(row["vix_change5"]) <= 0
        and float(row["sector_median_ret1"]) > 0
        and float(row["factor_median_ret1"]) > 0
    )
    if repairing:
        return "REPAIRING"
    if bool(row["v2_stabilizing"]):
        return "STABILIZING"
    if float(row["b50_change3"]) < 0 and float(row["vix_change5"]) > 0:
        return "WORSENING"
    return "MIXED"


def _factor_state(row: pd.Series) -> list[str]:
    labels: list[str] = []
    if bool(row["v2_momentum_reset"]):
        labels.append("MOMENTUM RESET")
    if bool(row["v2_growth_reset"]):
        labels.append("GROWTH RESET")
    if bool(row["v2_quality_over_momentum"]):
        labels.append("QUALITY LEADERSHIP")
    if bool(row["v2_small_vs_large_reset"]):
        labels.append("SMALL VS LARGE RESET")
    return labels or ["NO MATERIAL FACTOR RESET"]


def _market_damage(row: pd.Series) -> str:
    weak_count = sum(
        [
            float(row["spy_dd20"]) <= -0.01,
            float(row["B50"]) <= 0.50,
            float(row["vix_change5"]) >= 0.10,
            float(row["curve_ratio"]) >= 1.0,
        ]
    )
    if float(row["spy_dd20"]) <= -0.05 and weak_count >= 3:
        return "HEAVY"
    if float(row["spy_dd20"]) <= -0.02 or weak_count >= 2:
        return "MODERATE"
    if weak_count >= 1:
        return "LIGHT"
    return "NONE"


def _unified_signal(analog_decision: str, weak: bool, row: pd.Series) -> tuple[str, str, str]:
    """One operational decision from broad-market, internal, stabilization, and analog evidence.

    Broad-market timing retains the previously validated mapping. Internal-only re-entry
    requires a meaningful stabilized reset plus stronger YES/STRONG YES analog confirmation.
    Developing internal states become WAIT rather than a competing secondary engine.
    """
    if weak:
        signal, text = strategy_signal(analog_decision, True)
        return signal, text, "BROAD_AND_INTERNAL_COMBINED"

    meaningful = bool(row["v2_meaningful"])
    developing = bool(row["v2_developing"])
    stabilizing = bool(row["v2_stabilizing"])

    if meaningful and stabilizing and analog_decision in {"YES", "STRONG YES"}:
        return (
            "RE-ENTER",
            "meaningful internal sector/factor damage has stabilized and historical analogs support re-entry even though headline SPY damage is shallow",
            "INTERNAL_RESET_CONFIRMED",
        )
    if developing:
        return (
            "WAIT",
            "internal sector/factor conditions show a developing reset, but the combined evidence is not yet strong enough for re-entry",
            "INTERNAL_RESET_DEVELOPING",
        )
    return "NO RE-ENTRY SETUP", "no meaningful correction or internal reset is currently present", "NO_SETUP"


def _signal_snapshot(row: pd.Series) -> dict[str, Any]:
    sectors = {
        symbol: {
            "drawdown_20d": float(row[f"{symbol}_dd20"]),
            "drawdown_60d": float(row[f"{symbol}_dd60"]),
            "relative_strength_20d_vs_spy": float(row[f"{symbol}_rs20"]),
            "relative_strength_60d_vs_spy": float(row[f"{symbol}_rs60"]),
        }
        for symbol in SECTORS
    }
    factors = {
        symbol: {
            "drawdown_20d": float(row[f"{symbol}_dd20"]),
            "drawdown_60d": float(row[f"{symbol}_dd60"]),
            "relative_strength_20d_vs_spy": float(row[f"{symbol}_rs20"]),
            "relative_strength_60d_vs_spy": float(row[f"{symbol}_rs60"]),
        }
        for symbol in FACTORS
    }
    return {
        "headline_market": {
            "spy_drawdown_20d": float(row["spy_dd20"]),
            "spy_return_5d": float(row["spy_ret5"]),
        },
        "breadth": {
            "pct_sp500_above_50dma": float(row["B50"]),
            "pct_sp500_above_200dma": float(row["B200"]),
            "breadth_1d_change": float(row["b50_change1"]),
            "breadth_3d_change": float(row["b50_change3"]),
        },
        "volatility": {
            "vix_5d_change": float(row["vix_change5"]),
            "vix_vix3m_ratio": float(row["curve_ratio"]),
        },
        "sector_aggregates": {
            "damage_count_2pct": int(row["sector_damage_2"]),
            "damage_count_3pct": int(row["sector_damage_3"]),
            "damage_count_5pct": int(row["sector_damage_5"]),
            "damage_share_2pct": float(row["v2_sector_damage_share_2"]),
            "damage_share_3pct": float(row["v2_sector_damage_share_3"]),
            "median_drawdown_20d": float(row["v2_sector_median_dd"]),
            "median_drawdown_60d": float(row["sector_median_dd60"]),
            "dispersion_20d": float(row["sector_dispersion20"]),
            "dispersion_percentile": float(row["sector_dispersion_pct"]),
            "relative_strength_dispersion": float(row["v2_sector_rs_dispersion"]),
            "repair_count": int(row["sector_repair"]),
            "repair_share": float(row["v2_sector_repair_share"]),
            "median_1d_return": float(row["sector_median_ret1"]),
        },
        "factor_aggregates": {
            "damage_count_2pct": int(row["factor_damage_2"]),
            "damage_count_3pct": int(row["factor_damage_3"]),
            "damage_share_2pct": float(row["v2_factor_damage_share_2"]),
            "damage_share_3pct": float(row["v2_factor_damage_share_3"]),
            "median_drawdown_20d": float(row["v2_factor_median_dd"]),
            "median_drawdown_60d": float(row["factor_median_dd60"]),
            "dispersion_20d": float(row["factor_dispersion20"]),
            "relative_strength_dispersion": float(row["v2_factor_rs_dispersion"]),
            "repair_count": int(row["factor_repair"]),
            "repair_share": float(row["v2_factor_repair_share"]),
            "median_1d_return": float(row["factor_median_ret1"]),
        },
        "rotation_leadership": {
            "momentum_relative_20d": float(row["momentum_relative_20"]),
            "quality_minus_momentum_20d": float(row["quality_minus_momentum_20"]),
            "growth_minus_value_20d": float(row["growth_minus_value_20"]),
            "small_vs_large_relative_20d": float(row["IWM_rs20"]),
            "rotation_count": int(row["v2_rotation_count"]),
        },
        "sectors": sectors,
        "factors": factors,
    }


def build_snapshot(require_same_day: bool = True) -> dict[str, Any]:
    """Build the one authoritative daily RE-ENTRY engine object."""
    if require_same_day:
        _install_live_data_hardening()
    base, freshness = feature_frame(return_metadata=True, require_same_day=require_same_day)
    target = base.index.max()
    frame = _build_unified_frame(base, require_same_day=require_same_day)
    if target not in frame.index:
        raise RuntimeError(f"Unified sector/factor state is unavailable for {target.date()}")
    row = frame.loc[target]

    analogs = analogs_for_date(base, target)
    decision_stats = summarize_analogs(base, analogs)
    extended_evidence = summarize_extended_evidence(base, analogs)
    analog_decision, analog_interpretation, diagnostics = decision_from_analogs(decision_stats, row)
    weak, weak_reasons = weakness_context(row)
    signal, signal_text, setup_source = _unified_signal(analog_decision, weak, row)

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "as_of": str(target.date()),
        "strategy": "RE-ENTRY",
        "question": "Does it make sense to put cash back into the market right now?",
        "data_freshness": freshness,
        "signal": signal,
        "signal_interpretation": signal_text,
        "setup_source": setup_source,
        "market_damage": _market_damage(row),
        "internal_reset": _internal_reset(row),
        "selling_pressure": _selling_pressure(row),
        "factor_leadership_state": _factor_state(row),
        "analog_decision": analog_decision,
        "analog_interpretation": analog_interpretation,
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
        "signal_snapshot": _signal_snapshot(row),
        "analog_count": int(len(analogs)),
        "analogs": _analog_rows(analogs),
        "forward_analog_outcomes": decision_stats,
        "extended_forward_evidence": extended_evidence,
        "evidence_horizons": list(EVIDENCE_HORIZONS),
        "drawdown_definition": "close-to-close maximum adverse excursion from hypothetical close t+1 entry through each horizon",
        "decision_diagnostics": diagnostics,
        "implementation": {
            "evaluate": "after each market close",
            "freshness_policy": "all market, breadth, sector, and factor inputs must resolve to the latest completed U.S. equity session or no current signal is emitted",
            "headline_market_inputs": [
                "SPY 20D drawdown", "SPY 5D return", "% S&P above 50DMA", "% S&P above 200DMA",
                "1D breadth change", "3D breadth change", "VIX 5D change", "VIX/VIX3M",
            ],
            "sector_universe": SECTORS,
            "factor_universe": FACTORS,
            "sector_factor_inputs": [
                "20D drawdowns", "60D drawdowns", "20D relative strength vs SPY",
                "60D relative strength vs SPY", "damage breadth", "repair breadth",
                "cross-sectional dispersion", "median daily repair behavior",
            ],
            "rotation_inputs": [
                "Momentum relative to SPY", "Quality minus Momentum", "Growth minus Value", "Small vs Large",
            ],
            "reentry_rule": "one unified decision from headline weakness, internal sector/factor reset, stabilization, and historical analog evidence",
            "historical_analogs": "40 nearest prior broad-market states; 5/7/10/15/30/60D SPY and QQQ outcome evidence",
            "execution": "actionable for the next trading session; historical validation assumed close t+1 execution and 10 bps round-trip friction",
            "exit_rule": "none; this is an entry-timing framework for redeploying cash, not a forced short-horizon swing exit",
            "large_corrections": "fully included; there is no maximum drawdown exclusion",
            "rolling_corrections": "included through breadth plus sector/factor damage and rotation even when headline SPY drawdown is shallow",
            "no_fitted_black_box_score": True,
        },
        "historical_validation": historical_validation_block(),
        "proxy_caveat": PROXY_CAVEAT,
        "research_only": True,
        "caveats": [
            "true breadth history begins in September 2016",
            "historical evidence supports decision timing, not guaranteed returns",
            "drawdown statistics are based on daily closes, not intraday lows",
            "internal-only RE-ENTER is a research-stage unified policy and must be validated before production promotion",
            PROXY_CAVEAT,
        ],
    }
    validate_snapshot(snapshot, require_same_day=require_same_day)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any], require_same_day: bool = True) -> None:
    required = {
        "schema_version", "engine_version", "as_of", "signal", "analog_decision",
        "market_state", "current_inputs", "signal_snapshot", "internal_reset",
        "selling_pressure", "analogs", "extended_forward_evidence", "evidence_horizons",
        "data_freshness", "proxy_caveat",
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
        raise ValueError("Evidence horizons do not match engine contract")
    if len(snapshot["analogs"]) != 40:
        raise ValueError(f"Expected 40 analogs, found {len(snapshot['analogs'])}")
    if require_same_day and not snapshot["data_freshness"].get("same_day_complete", False):
        raise ValueError("Live snapshot is not same-day complete")
    if snapshot["proxy_caveat"] != PROXY_CAVEAT:
        raise ValueError("Required sector/factor proxy caveat is missing or altered")
    for symbol in ("SPY", "QQQ"):
        evidence = snapshot["extended_forward_evidence"].get(symbol, {})
        for horizon in EVIDENCE_HORIZONS:
            cell = evidence.get(str(horizon))
            if not cell or int(cell.get("n", 0)) <= 0:
                raise ValueError(f"Missing {symbol} {horizon}D evidence")
            for field in ("median_return", "positive_rate", "median_max_drawdown", "p10_max_drawdown", "worst_max_drawdown"):
                if field not in cell:
                    raise ValueError(f"Missing {symbol} {horizon}D field {field}")
