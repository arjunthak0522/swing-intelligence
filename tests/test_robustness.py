import numpy as np
from swing_intelligence.robustness import block_bootstrap_edge, benjamini_hochberg


def test_bootstrap_detects_clear_positive_edge():
    rng=np.random.default_rng(1)
    s=rng.normal(.02,.01,200); b=rng.normal(.002,.01,1500)
    r=block_bootstrap_edge(s,b,iterations=300,seed=2)
    assert r.observed_median_edge > 0
    assert r.ci_low > 0


def test_bh_controls_family():
    t=benjamini_hochberg({"a":.001,"b":.01,"c":.7}, alpha=.05)
    assert bool(t.loc[t.signal=="a","passes_fdr"].iloc[0])
    assert not bool(t.loc[t.signal=="c","passes_fdr"].iloc[0])
