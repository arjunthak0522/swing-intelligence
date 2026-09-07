from __future__ import annotations

import json
from pathlib import Path

from reentry_engine import build_snapshot
from reentry_insights import add_market_insights
from reentry_opportunity_evidence import attach_opportunity_evidence
from reentry_outperformance_live import add_outperformance_highlights
from reentry_rsp_breadth import add_rsp_breadth


def main() -> None:
    snapshot = build_snapshot(require_same_day=True)
    snapshot = add_rsp_breadth(snapshot)
    snapshot = add_market_insights(snapshot)
    snapshot = attach_opportunity_evidence(snapshot)
    snapshot = add_outperformance_highlights(snapshot)
    out = Path("artifacts/reentry")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "live_completed_close.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
