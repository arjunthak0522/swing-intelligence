import pandas as pd

from swing_intelligence.validation import validate_market_history, validate_volatility_index_history


def _frame(values):
    idx = pd.bdate_range('2020-01-01', periods=len(values))
    s = pd.Series(values, index=idx, dtype=float)
    return pd.DataFrame({
        'open': s,
        'high': s,
        'low': s,
        'close': s,
        'volume': 0.0,
    })


def test_vix_validator_allows_large_legitimate_jump_but_etf_validator_does_not():
    values = [15.0] * 1000
    values[500] = 32.0
    df = _frame(values)

    out = validate_volatility_index_history(df, min_rows=1000)
    assert out['max_abs_daily_return'] > 1.0

    try:
        validate_market_history(df, min_rows=1000)
    except ValueError as exc:
        assert 'Implausible daily close move' in str(exc)
    else:
        raise AssertionError('ETF validator should reject the same >100% one-day move')


def test_vix_validator_rejects_implausible_absolute_level():
    values = [15.0] * 999 + [150.0]
    df = _frame(values)
    try:
        validate_volatility_index_history(df, min_rows=1000)
    except ValueError as exc:
        assert 'outside plausible range' in str(exc)
    else:
        raise AssertionError('Expected implausible VIX level to be rejected')
