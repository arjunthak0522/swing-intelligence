from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TOOLS = Path(__file__).resolve().parents[1] / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import reentry_opportunity_evidence as opportunity
import reentry_sector_subsector_ranking as ranking
import reentry_walkforward_validation as walkforward


def _synthetic_frame(n: int = 380) -> pd.DataFrame:
    idx = pd.bdate_range("2020-01-02", periods=n)
    x = np.arange(n, dtype=float)
    data: dict[str, np.ndarray] = {
        "SPY": 300.0 + x * 0.25 + np.sin(x / 8.0),
        "QQQ": 200.0 + x * 0.35 + np.cos(x / 7.0),
    }
    for i, col in enumerate(walkforward.FEATURES):
        data[col] = (x / max(n - 1, 1)) + 0.05 * np.sin(x / (5.0 + i)) + i * 0.001
    return pd.DataFrame(data, index=idx)


def test_prior_only_analog_warmup_returns_unavailable_before_minimum_history() -> None:
    frame = _synthetic_frame()
    first_valid_pos = walkforward.MIN_HISTORY + walkforward.EXCLUSION_SESSIONS

    assert walkforward.historical_analogs(frame, first_valid_pos - 1) is None

    analogs = walkforward.historical_analogs(frame, first_valid_pos)
    assert analogs is not None
    assert len(analogs) == walkforward.K_ANALOGS

    cutoff = first_valid_pos - walkforward.EXCLUSION_SESSIONS
    analog_positions = [frame.index.get_loc(d) for d in analogs.index]
    assert max(analog_positions) < cutoff


def test_generate_decisions_excludes_warmup_dates_and_never_selects_future_analogs(monkeypatch) -> None:
    frame = _synthetic_frame()
    seen_positions: list[tuple[int, int]] = []
    original = walkforward.historical_analogs

    def checked_analogs(local_frame: pd.DataFrame, pos: int):
        analogs = original(local_frame, pos)
        if analogs is not None:
            max_analog_pos = max(local_frame.index.get_loc(d) for d in analogs.index)
            seen_positions.append((pos, max_analog_pos))
        return analogs

    monkeypatch.setattr(walkforward, "historical_analogs", checked_analogs)
    monkeypatch.setattr(
        walkforward,
        "decision_from_analogs",
        lambda stats, row: ("YES", "synthetic", {}),
    )

    decisions = walkforward.generate_decisions(frame)
    first_valid_pos = walkforward.MIN_HISTORY + walkforward.EXCLUSION_SESSIONS

    assert not decisions.empty
    assert decisions.index.min() == frame.index[first_valid_pos]
    assert all(frame.index.get_loc(d) >= first_valid_pos for d in decisions.index)
    assert seen_positions
    assert all(max_analog_pos < pos - walkforward.EXCLUSION_SESSIONS for pos, max_analog_pos in seen_positions)


def test_ranking_uses_only_dates_present_in_canonical_signal_history() -> None:
    frame = _synthetic_frame(420)
    prices = pd.DataFrame(
        {
            "SPY": frame["SPY"],
            "XLK": 150.0 + np.arange(len(frame)) * 0.20 + np.sin(np.arange(len(frame)) / 9.0),
        },
        index=frame.index,
    )
    first_valid_pos = walkforward.MIN_HISTORY + walkforward.EXCLUSION_SESSIONS
    signal_index = frame.index[first_valid_pos:]
    signals = pd.Series("WAIT", index=signal_index, dtype=object)
    signals.iloc[0:2] = "RE-ENTER"
    signals.iloc[15:17] = "RE-ENTER"

    starts = ranking.episode_starts(signals)
    assert starts
    assert min(starts) == signal_index[0]
    assert all(d >= signal_index[0] for d in starts)

    independent = ranking.independent_starts(starts, prices.index)
    results = ranking.evaluate_universe(prices, independent, ["XLK"], "sector")

    assert results["XLK"]["horizons"]["5"]["n"] > 0
    assert results["XLK"]["horizons"]["10"]["n"] > 0


def test_opportunity_evidence_rejects_nonfinite_current_repair_metrics(tmp_path: Path) -> None:
    ranking_path = tmp_path / "ranking.json"
    ranking_path.write_text(
        json.dumps(
            {
                "methodology": {"signal": "canonical RE-ENTRY"},
                "sector_results": {
                    "XLK": {
                        "label": "Technology",
                        "horizons": {"10": {"n": 5, "median": 0.01, "positive_rate": 0.6}},
                    },
                    "XLC": {
                        "label": "Communication Services",
                        "horizons": {"10": {"n": 5, "median": 0.02, "positive_rate": 0.7}},
                    },
                },
                "subsector_results": {
                    "SMH": {
                        "label": "Semiconductors",
                        "parent": "XLK",
                        "horizons": {"10": {"n": 5, "median": 0.03, "positive_rate": 0.8}},
                    },
                    "BAD": {
                        "label": "Unavailable proxy",
                        "parent": "XLK",
                        "horizons": {"10": {"n": 5, "median": 0.01, "positive_rate": 0.6}},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    snapshot = {
        "subsector_intelligence": {
            "by_sector": {
                "XLK": {"damage_share_3pct": 0.75, "repair_share": 0.50},
                "XLC": {"damage_share_3pct": float("nan"), "repair_share": float("nan")},
            },
            "proxies": {
                "SMH": {
                    "repairing": True,
                    "label": "Semiconductors",
                    "parent_sector": "XLK",
                    "drawdown_20d": -0.04,
                    "return_5d": 0.02,
                },
                "BAD": {
                    "repairing": True,
                    "label": "Unavailable proxy",
                    "parent_sector": "XLK",
                    "drawdown_20d": float("nan"),
                    "return_5d": float("nan"),
                },
            },
        }
    }

    out = opportunity.attach_opportunity_evidence(snapshot, ranking_path)
    sectors = out["opportunity_evidence"]["sectors"]
    subsectors = out["opportunity_evidence"]["subsectors"]

    assert [row["symbol"] for row in sectors] == ["XLK"]
    assert [row["symbol"] for row in subsectors] == ["SMH"]
    assert sectors[0]["historical_after_reentry"]["10"]["n"] == 5
    assert subsectors[0]["historical_after_reentry"]["10"]["n"] == 5
