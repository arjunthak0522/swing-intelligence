import numpy as np
import pandas as pd


def forward_path_stats(df: pd.DataFrame, entries, horizon: int) -> pd.DataFrame:
    """Calculate forward return, MAE and MFE from close entry to future closes.

    MAE/MFE use daily low/high relative to entry close through the requested horizon.
    Entries lacking a complete future path are excluded.
    """
    rows = []
    loc = {idx: i for i, idx in enumerate(df.index)}
    for dt in entries:
        i = loc.get(dt)
        if i is None or i + horizon >= len(df):
            continue
        entry = float(df["close"].iloc[i])
        future = df.iloc[i + 1:i + horizon + 1]
        end_close = float(df["close"].iloc[i + horizon])
        rows.append({
            "date": dt,
            "forward_return": end_close / entry - 1,
            "mae": float((future["low"] / entry - 1).min()),
            "mfe": float((future["high"] / entry - 1).max()),
        })
    if not rows:
        return pd.DataFrame(columns=["forward_return", "mae", "mfe"])
    return pd.DataFrame(rows).set_index("date")


def summarize_forward_paths(paths: pd.DataFrame) -> dict:
    if paths.empty:
        return {"n": 0}
    r = paths["forward_return"]
    return {
        "n": int(len(paths)),
        "win_probability": float((r > 0).mean()),
        "mean_return": float(r.mean()),
        "median_return": float(r.median()),
        "p10": float(r.quantile(.10)),
        "p25": float(r.quantile(.25)),
        "p75": float(r.quantile(.75)),
        "p90": float(r.quantile(.90)),
        "median_mae": float(paths["mae"].median()),
        "p10_mae": float(paths["mae"].quantile(.10)),
        "median_mfe": float(paths["mfe"].median()),
        "p90_mfe": float(paths["mfe"].quantile(.90)),
    }
