from __future__ import annotations

import json
from pathlib import Path

from reentry_engine import build_snapshot

DATA_ROOT = Path("data/reentry")
HISTORY_ROOT = DATA_ROOT / "history"


def persist_snapshot(snapshot: dict) -> tuple[dict, list[Path], bool]:
    """Persist one completed-session snapshot without ever rewriting history.

    If the immutable date already exists, that stored record remains authoritative.
    Reruns for the same completed session are therefore idempotent even if a live
    upstream source later republishes slightly different metadata for that date.
    """
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    HISTORY_ROOT.mkdir(parents=True, exist_ok=True)

    as_of = snapshot["as_of"]
    canonical = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    history_path = HISTORY_ROOT / f"{as_of}.json"
    latest_path = DATA_ROOT / "latest.json"
    reused_existing = False

    if history_path.exists():
        authoritative = json.loads(history_path.read_text(encoding="utf-8"))
        reused_existing = True
    else:
        history_path.write_text(canonical, encoding="utf-8")
        authoritative = snapshot

    authoritative_text = json.dumps(authoritative, indent=2, sort_keys=True) + "\n"
    latest_path.write_text(authoritative_text, encoding="utf-8")

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
    return authoritative, [history_path, latest_path, index_path], reused_existing


def main() -> None:
    snapshot = build_snapshot(require_same_day=True)
    authoritative, paths, reused_existing = persist_snapshot(snapshot)
    print(json.dumps({
        "as_of": authoritative["as_of"],
        "engine_version": authoritative["engine_version"],
        "signal": authoritative["signal"],
        "analog_decision": authoritative["analog_decision"],
        "immutable_existing_reused": reused_existing,
        "written": [str(p) for p in paths],
    }, indent=2))


if __name__ == "__main__":
    main()
