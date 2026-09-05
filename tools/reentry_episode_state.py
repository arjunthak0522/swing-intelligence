from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yfinance as yf


def close_on(symbol: str, day: str) -> float:
    start = pd.Timestamp(day)
    end = start + pd.Timedelta(days=4)
    frame = yf.download(symbol, start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'), progress=False, auto_adjust=False)
    if frame.empty:
        raise RuntimeError(f'no price data for {symbol} on {day}')
    close = frame['Close']
    if getattr(close, 'ndim', 1) > 1:
        close = close.iloc[:, 0]
    idx = pd.to_datetime(close.index).normalize()
    target = pd.Timestamp(day).normalize()
    matches = close[idx == target]
    if matches.empty:
        raise RuntimeError(f'no regular-session close for {symbol} on {day}')
    return round(float(matches.iloc[-1]), 2)


def update(snapshot_path: Path, state_path: Path) -> dict | None:
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    as_of = snapshot['as_of']
    signal = snapshot['signal']
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else None

    if signal == 'RE-ENTER':
        if state is None or not state.get('active', False):
            state = {
                'episode_start': as_of,
                'favorable_through': as_of,
                'active': True,
                'ended_on': None,
                'entry_closes': {
                    'SPY': close_on('SPY', as_of),
                    'QQQ': close_on('QQQ', as_of),
                },
                'definition': 'One re-entry episode begins on the first RE-ENTER close after a non-RE-ENTER state. Consecutive RE-ENTER closes extend the same episode rather than creating new entries.',
                'price_definition': 'Regular-session close on the first signal day.',
            }
        else:
            state['favorable_through'] = as_of
            state['ended_on'] = None
    elif state is not None and state.get('active', False):
        state['active'] = False
        state['ended_on'] = as_of

    if state is not None:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', required=True)
    parser.add_argument('--state', required=True)
    args = parser.parse_args()
    print(json.dumps(update(Path(args.snapshot), Path(args.state)), indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
