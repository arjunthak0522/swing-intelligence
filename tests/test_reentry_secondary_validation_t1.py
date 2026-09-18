import importlib.util
import sys
from pathlib import Path

import pandas as pd

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "reentry_secondary_family_validation.py"
spec = importlib.util.spec_from_file_location("reentry_secondary_family_validation", MODULE_PATH)
validation = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(validation)


def test_final_daily_put_call_is_shifted_to_next_trading_session():
    sessions = pd.DatetimeIndex(["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"])
    observed = pd.Series([0.60, 0.81, 0.69, 0.75], index=sessions)
    available = validation.t_plus_one_available(observed, sessions)

    assert pd.isna(available.loc["2026-09-15"])
    assert available.loc["2026-09-16"] == 0.60
    assert available.loc["2026-09-17"] == 0.81
    assert available.loc["2026-09-18"] == 0.69
    # Sep 17's finalized 0.69 cannot be visible on Sep 17 itself.
    assert available.loc["2026-09-17"] != observed.loc["2026-09-17"]
