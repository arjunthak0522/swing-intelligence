from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np

from build_historical_episode_evidence import build_exact_policy, forward_return, CANONICAL_FORWARD_MEDIANS, CANONICAL_FINAL_POLICY_COUNT


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--canonical-root', default='canonical')
    args = p.parse_args()
    prices, df, dates, cooldown = build_exact_policy(Path(args.canonical_root).resolve() / 'tools')
    current = {}
    for sym in ('SPY','QQQ'):
        s = prices[sym].dropna()
        current[sym] = {}
        for h in (5,10,30,60):
            vals = [x for d in dates if (x := forward_return(s, d, h)) is not None]
            current[sym][str(h)] = {
                'n': len(vals),
                'median': float(np.median(vals)) if vals else None,
                'archived_median': CANONICAL_FORWARD_MEDIANS[sym][h],
                'difference': (float(np.median(vals)) - CANONICAL_FORWARD_MEDIANS[sym][h]) if vals else None,
            }
    result = {
        'archived_count': CANONICAL_FINAL_POLICY_COUNT,
        'rebuilt_count': len(dates),
        'cooldown': cooldown,
        'sample_start': str(df.index.min().date()),
        'sample_end': str(df.index.max().date()),
        'forward_medians': current,
        'first_10_dates': [str(d.date()) for d in dates[:10]],
        'last_20_dates': [str(d.date()) for d in dates[-20:]],
    }
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/historical_policy_drift.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
