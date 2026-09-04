from __future__ import annotations

import json
from pathlib import Path

from reentry_commentary import build_prioritized_market_commentary
from reentry_early_entry_policy import apply_early_entry_bias
from reentry_engine import build_snapshot
from reentry_subsector_intelligence import enrich_snapshot_with_subsectors


def main() -> None:
    snapshot = build_snapshot(require_same_day=False)
    snapshot = apply_early_entry_bias(snapshot)
    snapshot = enrich_snapshot_with_subsectors(snapshot, require_same_day=False)
    snapshot["market_commentary"] = build_prioritized_market_commentary(snapshot)
    snapshot["research_only"] = True
    out = Path("artifacts/reentry")
    out.mkdir(parents=True, exist_ok=True)
    (out / "unified_latest.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(snapshot, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
