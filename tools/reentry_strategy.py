from __future__ import annotations

import json
from pathlib import Path

from reentry_engine import build_snapshot


def main() -> None:
    snapshot = build_snapshot(require_same_day=True)

    strategy_out = Path("artifacts/reentry_strategy")
    strategy_out.mkdir(parents=True, exist_ok=True)
    (strategy_out / "reentry_strategy.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    canonical_out = Path("artifacts/reentry_snapshot")
    canonical_out.mkdir(parents=True, exist_ok=True)
    (canonical_out / "latest.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
