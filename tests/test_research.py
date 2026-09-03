import numpy as np
import pandas as pd

from swing_intelligence.research import ResearchSplit, split_periods, survivor_table


def test_split_periods_no_overlap():
    idx = pd.date_range('2015-01-01', '2024-12-31', freq='B')
    df = pd.DataFrame({'x': np.arange(len(idx))}, index=idx)
    p = split_periods(df, ResearchSplit('2018-12-31','2021-12-31'))
    assert p['train'].index.max() <= pd.Timestamp('2018-12-31')
    assert p['validation'].index.min() > pd.Timestamp('2018-12-31')
    assert p['holdout'].index.min() > pd.Timestamp('2021-12-31')


def test_survivor_requires_validation_and_holdout():
    def result(name, n, edge, win):
        return {'name': name, 'horizons': {10: {'n': n, 'median_excess_edge': edge, 'win_probability_edge': win}}}
    ev = {
        'train': {'results':[result('a',100,.01,.05), result('b',100,.02,.06)]},
        'validation': {'results':[result('a',50,.01,.03), result('b',50,-.01,.04)]},
        'holdout': {'results':[result('a',45,.005,.02), result('b',45,.02,.05)]},
    }
    table = survivor_table(ev, min_n=30)
    a = table.loc[table.signal=='a'].iloc[0]
    b = table.loc[table.signal=='b'].iloc[0]
    assert bool(a.survives)
    assert not bool(b.survives)
