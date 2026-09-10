from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY = Path("data/reentry/exhaustion_history.csv")
OUTCOMES = Path("data/reentry/exhaustion_outcomes.csv")
REPORT = Path("artifacts/selling_exhaustion_reliability/reliability_report.json")
STATUS = Path("data/reentry/exhaustion_reliability.json")

CORE_FIELDS = (
    "MMFD", "MMTW", "SPXA20R", "SPXA50R", "BPSPX",
    "NYMO", "NAMO", "NYUD", "NAUD",
    "NYUPV", "NYDNV", "NAUPV", "NADNV",
)

MIN_PROSPECTIVE_ROWS = 60
MIN_WASHOUT_ROWS = 20
MIN_MATURED_10D = 20
MIN_MATURED_30D = 12
MAX_MISSING_RATE = 0.05


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def present(value: str | None) -> bool:
    return value not in (None, "", "nan", "NaN", "None")


def float_or_none(value: str | None) -> float | None:
    try:
        if not present(value):
            return None
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return None


def metric(rows: list[dict[str, str]], field: str) -> dict:
    vals = [float_or_none(r.get(field)) for r in rows]
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "positive_rate": None}
    vals = sorted(vals)
    n = len(vals)
    mid = n // 2
    median = vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2
    return {
        "n": n,
        "mean": sum(vals) / n,
        "median": median,
        "positive_rate": sum(v > 0 for v in vals) / n,
    }


def main() -> None:
    history = read_csv(HISTORY)
    outcomes = read_csv(OUTCOMES)

    total_cells = max(1, len(history) * len(CORE_FIELDS))
    missing_cells = sum(1 for row in history for field in CORE_FIELDS if not present(row.get(field)))
    missing_rate = missing_cells / total_cells

    oversold_history = [r for r in history if r.get("state") == "OVERSOLD"]
    washout_history = [r for r in history if r.get("state") in {"WASHOUT", "CONFIRMED"}]
    confirmed_history = [r for r in history if r.get("state") == "CONFIRMED"]

    matured_10 = [r for r in outcomes if present(r.get("SPY_10D")) and present(r.get("QQQ_10D"))]
    matured_30 = [r for r in outcomes if present(r.get("SPY_30D")) and present(r.get("QQQ_30D"))]

    gates = {
        "source_completeness": {
            "pass": missing_rate <= MAX_MISSING_RATE,
            "value": missing_rate,
            "requirement": f"missing core-field rate <= {MAX_MISSING_RATE:.0%}",
        },
        "prospective_sample": {
            "pass": len(history) >= MIN_PROSPECTIVE_ROWS,
            "value": len(history),
            "requirement": f">= {MIN_PROSPECTIVE_ROWS} completed daily snapshots",
        },
        "washout_go_sample": {
            "pass": len(washout_history) >= MIN_WASHOUT_ROWS,
            "value": len(washout_history),
            "requirement": f">= {MIN_WASHOUT_ROWS} WASHOUT/CONFIRMED early-go observations",
        },
        "matured_10d_sample": {
            "pass": len(matured_10) >= MIN_MATURED_10D,
            "value": len(matured_10),
            "requirement": f">= {MIN_MATURED_10D} observations with both SPY/QQQ 10D outcomes",
        },
        "matured_30d_sample": {
            "pass": len(matured_30) >= MIN_MATURED_30D,
            "value": len(matured_30),
            "requirement": f">= {MIN_MATURED_30D} observations with both SPY/QQQ 30D outcomes",
        },
    }

    sample_ready = all(g["pass"] for g in gates.values())

    state_metrics = {}
    for state in ("OVERSOLD", "WASHOUT", "CONFIRMED"):
        rows = [r for r in outcomes if r.get("state") == state]
        state_metrics[state] = {
            "rows": len(rows),
            "SPY_5D": metric(rows, "SPY_5D"),
            "SPY_10D": metric(rows, "SPY_10D"),
            "SPY_30D": metric(rows, "SPY_30D"),
            "SPY_60D": metric(rows, "SPY_60D"),
            "QQQ_5D": metric(rows, "QQQ_5D"),
            "QQQ_10D": metric(rows, "QQQ_10D"),
            "QQQ_30D": metric(rows, "QQQ_30D"),
            "QQQ_60D": metric(rows, "QQQ_60D"),
        }

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "official_signal_modified": False,
        "framework": "SELLING EXHAUSTION",
        "semantics": {
            "OVERSOLD": "stretched internals but no turn yet",
            "WASHOUT": "first internal turn after oversold - early GO candidate",
            "CONFIRMED": "later corroboration after the early GO candidate",
        },
        "architecture": {
            "oversold": ["MMFD", "MMTW", "SPXA20R", "SPXA50R", "BPSPX", "NYMO", "NAMO"],
            "selling_pressure": ["NYUD", "NAUD", "NYUPV/NYDNV", "NAUPV/NADNV"],
            "immediate_turn": ["fast breadth recovery", "McClellan recovery", "net-volume recovery"],
            "anti_double_counting": "Correlated raw indicators are grouped into families before state classification.",
        },
        "data": {
            "history_rows": len(history),
            "oversold_rows": len(oversold_history),
            "washout_go_rows": len(washout_history),
            "confirmed_rows": len(confirmed_history),
            "core_missing_rate": missing_rate,
            "matured_10d_rows": len(matured_10),
            "matured_30d_rows": len(matured_30),
        },
        "gates": gates,
        "sample_ready_for_promotion_review": sample_ready,
        "paired_superiority_gate": {
            "pass": False,
            "status": "NOT_YET_EVALUABLE",
            "requirement": "Compare first WASHOUT date directly with frozen RE-ENTRY date. WASHOUT must arrive earlier often enough to matter without materially worsening false starts or downside tails.",
        },
        "promotion_status": "RESEARCH_ONLY_DO_NOT_PROMOTE",
        "state_forward_metrics": state_metrics,
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2)
    REPORT.write_text(payload, encoding="utf-8")
    STATUS.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
