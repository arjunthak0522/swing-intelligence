from __future__ import annotations

import json
from pathlib import Path

from reentry_engine import build_snapshot

DATA_ROOT = Path("data/reentry")
HISTORY_ROOT = DATA_ROOT / "history"


def persist_snapshot(snapshot: dict) -> list[Path]:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    HISTORY_ROOT.mkdir(parents=True, exist_ok=True)

    as_of = snapshot["as_of"]
    canonical = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    history_path = HISTORY_ROOT / f"{as_of}.json"
    latest_path = DATA_ROOT / "latest.json"

    if history_path.exists():
        existing = history_path.read_text(encoding="utf-8")
        if existing != canonical:
            raise RuntimeError(
                f"Immutable snapshot already exists for {as_of} with different contents. "
                "Refusing to rewrite historical engine output."
            )
    else:
        history_path.write_text(canonical, encoding="utf-8")

    latest_path.write_text(canonical, encoding="utf-8")

    index_rows = []
    for path in sorted(HISTORY_ROOT.glob("*.json"), reverse=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        index_rows.append({
            "as_of": payload["as_of"],
            "engine_version": payload["engine_version"],
            "signal": payload["signal"],
            "analog_decision": payload["analog_decision"],
            "market_state": payload["market_state"],
            "weakness_present": payload["weakness_present"],
        })
    index_path = DATA_ROOT / "index.json"
    index_path.write_text(json.dumps(index_rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return [history_path, latest_path, index_path]


def main() -> None:
    snapshot = build_snapshot(require_same_day=True)
    paths = persist_snapshot(snapshot)
    print(json.dumps({
        "as_of": snapshot["as_of"],
        "engine_version": snapshot["engine_version"],
        "signal": snapshot["signal"],
        "analog_decision": snapshot["analog_decision"],
        "written": [str(p) for p in paths],
    }, indent=2))


if __name__ == "__main__":
    main()
