from __future__ import annotations

import json
from pathlib import Path

from reentry_engine import build_snapshot
from reentry_insights import add_market_insights


def main() -> None:
    snapshot = add_market_insights(build_snapshot(require_same_day=True))
    out = Path("artifacts/reentry")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "live_completed_close.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
