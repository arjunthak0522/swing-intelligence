from .features import compute_features
from .market_state import compute_cross_asset_features
from .regimes import classify_regime
from .analogs import historical_analogs
from .outcomes import forward_path_stats, summarize_forward_paths
from .tournament import SignalSpec, evaluate_signal, rank_signals, default_candidate_signals
from .backtest import backtest_long_only, benchmark_buy_hold

__all__ = [
    "compute_features", "compute_cross_asset_features", "classify_regime",
    "historical_analogs", "forward_path_stats", "summarize_forward_paths",
    "SignalSpec", "evaluate_signal", "rank_signals", "default_candidate_signals",
    "backtest_long_only", "benchmark_buy_hold",
]
