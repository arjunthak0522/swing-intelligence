#!/usr/bin/env python3
"""Compatibility launcher for the live data branch.

The authoritative RE-ENTRY decision engine lives on main at
`tools/reentry_unified_engine.py`. This branch stores generated intraday data and
retains this launcher only so the existing scheduler can execute the main engine
without maintaining a second copy of the decision logic.
"""
from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

ENGINE_URL = "https://raw.githubusercontent.com/arjunthak0522/swing-intelligence/main/tools/reentry_unified_engine.py"


def main() -> None:
    req = Request(ENGINE_URL, headers={"User-Agent": "RE-ENTRY-main-engine-loader/1.0"})
    with urlopen(req, timeout=20) as response:  # nosec - fixed repository URL
        source = response.read().decode("utf-8")
    namespace = {
        "__name__": "__main__",
        "__file__": str(Path(__file__).resolve()),
        "__package__": None,
    }
    exec(compile(source, ENGINE_URL, "exec"), namespace, namespace)


if __name__ == "__main__":
    main()
