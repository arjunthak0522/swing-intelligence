from __future__ import annotations

import json
from pathlib import Path

from reentry_early_entry_policy import apply_early_entry_bias
from reentry_engine import build_snapshot


def main() -> None:
    snapshot = build_snapshot(require_same_day=True)
    snapshot = apply_early_entry_bias(snapshot)
    out = Path("artifacts/reentry")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "live_completed_close.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(snapshot, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
