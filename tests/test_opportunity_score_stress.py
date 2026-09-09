from swing_intelligence.opportunity_score_stress import OpportunityStressConfig, stress_grid


def test_phase4b_stress_grid_is_predeclared_and_complete():
    cfg = OpportunityStressConfig(
        trigger_levels=(65, 70, 75),
        horizons=(20, 30, 40, 60),
        min_gaps=(20, 30, 40),
        cost_bps=(5.0, 10.0, 20.0),
    )
    grid = stress_grid(cfg)
    assert len(grid) == 108
    assert len(set(grid)) == 108
    assert (70, 30, 30, 10.0) in grid
