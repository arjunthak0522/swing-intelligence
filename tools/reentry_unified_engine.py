#!/usr/bin/env python3
"""Compatibility loader for the live-data branch.

The authoritative RE-ENTRY decision engine remains on main. This module loads that
source without executing its CLI entrypoint during import, then re-exports the
canonical functions so regression tests and the scheduler use exactly one engine.
"""
from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

ENGINE_URL = "https://raw.githubusercontent.com/arjunthak0522/swing-intelligence/main/tools/reentry_unified_engine.py"


def load_engine_namespace() -> dict:
    req = Request(ENGINE_URL, headers={"User-Agent": "RE-ENTRY-main-engine-loader/1.0"})
    with urlopen(req, timeout=20) as response:  # nosec - fixed repository URL
        source = response.read().decode("utf-8")
    namespace = {
        "__name__": "reentry_unified_engine_canonical",
        "__file__": str(Path(__file__).resolve()),
        "__package__": None,
    }
    exec(compile(source, ENGINE_URL, "exec"), namespace, namespace)
    return namespace


_CANONICAL = load_engine_namespace()

evaluate = _CANONICAL["evaluate"]
allowed_window = _CANONICAL["allowed_window"]
market_phase = _CANONICAL["market_phase"]


def main() -> None:
    _CANONICAL["main"]()


if __name__ == "__main__":
    main()
