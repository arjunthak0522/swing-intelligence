from pathlib import Path
import os

from swing_intelligence.runner import fetch_universe, run_research

if __name__ == "__main__":
    if not os.getenv("TWELVE_DATA_API_KEY"):
        raise SystemExit("TWELVE_DATA_API_KEY is required for the provenance-checked research run")
    root = Path(__file__).parent
    frames = fetch_universe(root / "data" / "cache")
    summary = run_research(frames, root / "artifacts" / "research")
    print(summary)
