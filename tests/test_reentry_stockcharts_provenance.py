import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/reentry_exhaustion_intraday.py"

spec = importlib.util.spec_from_file_location("reentry_exhaustion_intraday", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def test_quote_provenance_preserves_vendor_metadata():
    quotes = {
        "$SPXA20R": {
            "close": 18.0,
            "as_of": "2026-09-10T15:45:00-04:00",
            "realtime": False,
            "cached": True,
        },
        "$NYMO": None,
    }
    out = module.quote_provenance(quotes)
    assert out["$SPXA20R"]["vendor_timestamp"] == "2026-09-10T15:45:00-04:00"
    assert out["$SPXA20R"]["realtime"] is False
    assert out["$SPXA20R"]["cached"] is True
    assert out["$SPXA20R"]["available"] is True
    assert out["$NYMO"]["available"] is False
