from __future__ import annotations

import json
from pathlib import Path

DATA_ROOT = Path("data/reentry")


def build_payload() -> dict:
    snapshot_path = DATA_ROOT / "latest.json"
    if not snapshot_path.exists():
        raise FileNotFoundError("data/reentry/latest.json is missing")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    as_of = snapshot["as_of"]
    realized_path = DATA_ROOT / "realized" / f"{as_of}.json"
    realized = (
        json.loads(realized_path.read_text(encoding="utf-8"))
        if realized_path.exists()
        else {"as_of": as_of, "engine_version": snapshot["engine_version"], "outcomes": {"SPY": {}, "QQQ": {}}}
    )
    return {
        "snapshot": snapshot,
        "realized": realized,
    }


def main() -> None:
    out = Path("artifacts/reentry_strategy/supabase_payload.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_payload()
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "as_of": payload["snapshot"]["as_of"],
        "engine_version": payload["snapshot"]["engine_version"],
        "analogs": len(payload["snapshot"].get("analogs", [])),
        "realized_cells": sum(
            len(payload["realized"].get("outcomes", {}).get(symbol, {}))
            for symbol in ("SPY", "QQQ")
        ),
        "output": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()
