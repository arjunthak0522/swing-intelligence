from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

# Liquid ETF proxies used to look beneath the 11 headline sector ETFs.
# These are diagnostics, not proprietary point-in-time industry indexes.
SUBSECTOR_GROUPS: dict[str, list[tuple[str, str]]] = {
    "XLC": [("FDN", "Internet"), ("IYZ", "Telecom"), ("PBS", "Media")],
    "XLY": [("XRT", "Retail"), ("ITB", "Homebuilders"), ("PEJ", "Leisure & Entertainment")],
    "XLP": [("PBJ", "Food & Beverage"), ("RHS", "Equal-Weight Consumer Staples")],
    "XLE": [("XOP", "Oil & Gas Exploration/Production"), ("OIH", "Oil Services"), ("CRAK", "Refiners")],
    "XLF": [("KRE", "Regional Banks"), ("KBE", "Banks"), ("IAI", "Broker-Dealers"), ("KIE", "Insurance")],
    "XLV": [("XBI", "Biotech"), ("IBB", "Large-Cap Biotech"), ("IHI", "Medical Devices"), ("IHF", "Healthcare Providers")],
    "XLI": [("ITA", "Aerospace & Defense"), ("XTN", "Transportation"), ("PAVE", "Infrastructure")],
    "XLB": [("XME", "Metals & Mining"), ("COPX", "Copper Miners"), ("SLX", "Steel")],
    "XLRE": [("REZ", "Residential & Specialized REITs"), ("SRVR", "Data Centers & Digital Infrastructure"), ("NETL", "Net Lease REITs")],
    "XLK": [("SMH", "Semiconductors"), ("IGV", "Software"), ("HACK", "Cybersecurity")],
    "XLU": [("RNRG", "Renewable Power Producers"), ("RYU", "Equal-Weight Utilities")],
}

SUBSECTOR_SYMBOLS = [symbol for groups in SUBSECTOR_GROUPS.values() for symbol, _ in groups]
PARENT_BY_SYMBOL = {
    symbol: parent for parent, groups in SUBSECTOR_GROUPS.items() for symbol, _ in groups
}
LABEL_BY_SYMBOL = {
    symbol: label for groups in SUBSECTOR_GROUPS.values() for symbol, label in groups
}

PROXY_CAVEAT = (
    "Subsector and industry histories use liquid ETF proxies. Coverage is intentionally diagnostic, "
    "can be uneven across sectors, and is not a proprietary point-in-time industry classification."
)


def _normalize_download(raw: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    if raw.empty:
        raise RuntimeError("Yahoo subsector price download failed")
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("Subsector close field missing from Yahoo download")
        closes = raw["Close"].copy()
    else:
        if len(symbols) != 1 or "Close" not in raw.columns:
            raise RuntimeError("Unexpected subsector price download shape")
        closes = raw[["Close"]].rename(columns={"Close": symbols[0]})
    closes.index = pd.to_datetime(closes.index).tz_localize(None).normalize()
    closes = closes.sort_index().apply(pd.to_numeric, errors="coerce")
    return closes


def load_subsector_prices(start: str = "2016-09-01") -> pd.DataFrame:
    import yfinance as yf

    symbols = sorted(set(SUBSECTOR_SYMBOLS + list(SUBSECTOR_GROUPS.keys()) + ["SPY", "QQQ"]))
    raw = yf.download(
        symbols,
        start=start,
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    closes = _normalize_download(raw, symbols)
    missing = [s for s in ["SPY", "QQQ", "SMH", "IGV"] if s not in closes.columns]
    if missing:
        raise RuntimeError(f"Required subsector proxies missing: {missing}")
    return closes


def _dd(prices: pd.DataFrame, window: int) -> pd.DataFrame:
    return prices / prices.rolling(window).max() - 1.0


def build_subsector_frame(prices: pd.DataFrame) -> pd.DataFrame:
    required = set(SUBSECTOR_SYMBOLS + list(SUBSECTOR_GROUPS.keys()) + ["SPY"])
    available = sorted(required.intersection(prices.columns))
    if "SPY" not in available:
        raise RuntimeError("SPY missing from subsector frame")

    px = prices[available].copy()
    ret1 = px.pct_change(1)
    ret5 = px.pct_change(5)
    ret20 = px.pct_change(20)
    ret60 = px.pct_change(60)
    dd20 = _dd(px, 20)
    dd60 = _dd(px, 60)

    out = pd.DataFrame(index=px.index)
    for symbol in SUBSECTOR_SYMBOLS:
        if symbol not in px.columns:
            continue
        parent = PARENT_BY_SYMBOL[symbol]
        if parent not in px.columns:
            continue
        out[f"sub_{symbol}_ret1"] = ret1[symbol]
        out[f"sub_{symbol}_ret5"] = ret5[symbol]
        out[f"sub_{symbol}_dd20"] = dd20[symbol]
        out[f"sub_{symbol}_dd60"] = dd60[symbol]
        out[f"sub_{symbol}_rs20_spy"] = ret20[symbol] - ret20["SPY"]
        out[f"sub_{symbol}_rs60_spy"] = ret60[symbol] - ret60["SPY"]
        out[f"sub_{symbol}_rs20_parent"] = ret20[symbol] - ret20[parent]
        out[f"sub_{symbol}_rs60_parent"] = ret60[symbol] - ret60[parent]
        out[f"sub_{symbol}_repair"] = (
            (dd20[symbol] <= -0.02)
            & (ret5[symbol] > 0)
            & ((ret20[symbol] - ret20[parent]) > (ret60[symbol] - ret60[parent]))
        )

    for parent, groups in SUBSECTOR_GROUPS.items():
        syms = [s for s, _ in groups if f"sub_{s}_dd20" in out.columns]
        if not syms:
            continue
        dd_cols = [f"sub_{s}_dd20" for s in syms]
        rs_cols = [f"sub_{s}_rs20_parent" for s in syms]
        repair_cols = [f"sub_{s}_repair" for s in syms]
        expected = len(groups)
        min_valid = max(2, math.ceil(expected * 0.67))
        valid_count = out[dd_cols].notna().sum(axis=1)
        valid = valid_count >= min_valid
        out[f"sub_{parent}_coverage"] = valid_count / expected
        out[f"sub_{parent}_damage_share_2"] = (out[dd_cols].le(-0.02) & out[dd_cols].notna()).sum(axis=1) / valid_count.replace(0, np.nan)
        out[f"sub_{parent}_damage_share_3"] = (out[dd_cols].le(-0.03) & out[dd_cols].notna()).sum(axis=1) / valid_count.replace(0, np.nan)
        out[f"sub_{parent}_median_dd20"] = out[dd_cols].median(axis=1)
        out[f"sub_{parent}_dispersion_parent_rs20"] = out[rs_cols].std(axis=1, ddof=0)
        repair_valid = out[dd_cols].notna()
        repair_values = out[repair_cols].astype(float).where(repair_valid.values)
        out[f"sub_{parent}_repair_share"] = repair_values.sum(axis=1, min_count=1) / valid_count.replace(0, np.nan)
        for suffix in [
            "damage_share_2",
            "damage_share_3",
            "median_dd20",
            "dispersion_parent_rs20",
            "repair_share",
        ]:
            out.loc[~valid, f"sub_{parent}_{suffix}"] = np.nan

    all_dd_cols = [f"sub_{s}_dd20" for s in SUBSECTOR_SYMBOLS if f"sub_{s}_dd20" in out.columns]
    all_repair_cols = [f"sub_{s}_repair" for s in SUBSECTOR_SYMBOLS if f"sub_{s}_repair" in out.columns]
    if all_dd_cols:
        valid_count = out[all_dd_cols].notna().sum(axis=1)
        expected = len(SUBSECTOR_SYMBOLS)
        broad_valid = valid_count >= math.ceil(expected * 0.80)
        out["subsector_coverage"] = valid_count / expected
        out["subsector_damage_share_2"] = (out[all_dd_cols].le(-0.02) & out[all_dd_cols].notna()).sum(axis=1) / valid_count.replace(0, np.nan)
        out["subsector_damage_share_3"] = (out[all_dd_cols].le(-0.03) & out[all_dd_cols].notna()).sum(axis=1) / valid_count.replace(0, np.nan)
        out["subsector_median_dd20"] = out[all_dd_cols].median(axis=1)
        out.loc[~broad_valid, ["subsector_damage_share_2", "subsector_damage_share_3", "subsector_median_dd20"]] = np.nan
    if all_repair_cols:
        valid_proxy = out[all_dd_cols].notna()
        repair_values = out[all_repair_cols].astype(float).where(valid_proxy.values)
        valid_count = valid_proxy.sum(axis=1)
        broad_valid = valid_count >= math.ceil(len(SUBSECTOR_SYMBOLS) * 0.80)
        out["subsector_repair_share"] = repair_values.sum(axis=1, min_count=1) / valid_count.replace(0, np.nan)
        out.loc[~broad_valid, "subsector_repair_share"] = np.nan
    return out


def _fmt_pct(value: float) -> str:
    return f"{value * 100:+.1f}%"


def subsector_snapshot(row: pd.Series) -> dict[str, Any]:
    by_sector: dict[str, Any] = {}
    flat: dict[str, Any] = {}
    for parent, groups in SUBSECTOR_GROUPS.items():
        members: dict[str, Any] = {}
        for symbol, label in groups:
            key = f"sub_{symbol}_dd20"
            if key not in row.index or pd.isna(row[key]):
                continue
            item = {
                "label": label,
                "parent_sector": parent,
                "drawdown_20d": float(row[f"sub_{symbol}_dd20"]),
                "drawdown_60d": float(row[f"sub_{symbol}_dd60"]),
                "return_1d": float(row[f"sub_{symbol}_ret1"]),
                "return_5d": float(row[f"sub_{symbol}_ret5"]),
                "relative_strength_20d_vs_spy": float(row[f"sub_{symbol}_rs20_spy"]),
                "relative_strength_20d_vs_parent": float(row[f"sub_{symbol}_rs20_parent"]),
                "relative_strength_60d_vs_parent": float(row[f"sub_{symbol}_rs60_parent"]),
                "repairing": bool(row[f"sub_{symbol}_repair"]),
            }
            members[symbol] = item
            flat[symbol] = item
        if members:
            by_sector[parent] = {
                "coverage": float(row.get(f"sub_{parent}_coverage", np.nan)),
                "damage_share_2pct": float(row.get(f"sub_{parent}_damage_share_2", np.nan)),
                "damage_share_3pct": float(row.get(f"sub_{parent}_damage_share_3", np.nan)),
                "median_drawdown_20d": float(row.get(f"sub_{parent}_median_dd20", np.nan)),
                "relative_strength_dispersion_vs_parent": float(row.get(f"sub_{parent}_dispersion_parent_rs20", np.nan)),
                "repair_share": float(row.get(f"sub_{parent}_repair_share", np.nan)),
                "members": members,
            }
    return {
        "aggregate": {
            "coverage": float(row.get("subsector_coverage", np.nan)),
            "damage_share_2pct": float(row.get("subsector_damage_share_2", np.nan)),
            "damage_share_3pct": float(row.get("subsector_damage_share_3", np.nan)),
            "median_drawdown_20d": float(row.get("subsector_median_dd20", np.nan)),
            "repair_share": float(row.get("subsector_repair_share", np.nan)),
        },
        "by_sector": by_sector,
        "proxies": flat,
        "proxy_caveat": PROXY_CAVEAT,
    }


def build_market_commentary(snapshot: dict[str, Any], subsectors: dict[str, Any]) -> dict[str, Any]:
    sector_items: list[dict[str, Any]] = []
    subsector_items: list[dict[str, Any]] = []
    factor_items: list[dict[str, Any]] = []

    sectors = snapshot.get("signal_snapshot", {}).get("sectors", {})
    for symbol, item in sectors.items():
        dd20 = float(item.get("drawdown_20d", 0.0))
        rs20 = float(item.get("relative_strength_20d_vs_spy", 0.0))
        group = subsectors.get("by_sector", {}).get(symbol, {})
        sub_damage_raw = group.get("damage_share_3pct", 0.0)
        sub_repair_raw = group.get("repair_share", 0.0)
        sub_damage = 0.0 if pd.isna(sub_damage_raw) else float(sub_damage_raw)
        sub_repair = 0.0 if pd.isna(sub_repair_raw) else float(sub_repair_raw)
        warranted = dd20 <= -0.03 or rs20 <= -0.02 or sub_damage >= 0.50 or sub_repair >= 0.50
        if not warranted:
            continue
        if sub_damage >= 0.50 and dd20 > -0.03:
            text = (
                f"{symbol} looks milder at the headline sector level ({_fmt_pct(dd20)} from its 20-day high), "
                f"but {sub_damage:.0%} of tracked groups are down at least 3%, indicating hidden internal damage."
            )
        elif sub_repair >= 0.50 and dd20 <= -0.02:
            text = (
                f"{symbol} remains corrected ({_fmt_pct(dd20)} from its 20-day high), while "
                f"{sub_repair:.0%} of tracked groups are repairing."
            )
        else:
            text = f"{symbol} is {_fmt_pct(dd20)} from its 20-day high with {_fmt_pct(rs20)} 20-day relative strength versus SPY."
        sector_items.append({"sector": symbol, "commentary": text})

    for symbol, item in subsectors.get("proxies", {}).items():
        dd20 = float(item["drawdown_20d"])
        rs_parent = float(item["relative_strength_20d_vs_parent"])
        repairing = bool(item["repairing"])
        if not (dd20 <= -0.03 or rs_parent <= -0.025 or repairing):
            continue
        if repairing:
            state = "is repairing after a meaningful reset"
        elif dd20 <= -0.05:
            state = "is in a deep internal correction"
        elif dd20 <= -0.03:
            state = "is in a meaningful internal correction"
        else:
            state = "is materially lagging its parent sector"
        subsector_items.append({
            "symbol": symbol,
            "label": item["label"],
            "parent_sector": item["parent_sector"],
            "commentary": (
                f"{symbol} ({item['label']}) {state}: {_fmt_pct(dd20)} from its 20-day high, "
                f"{_fmt_pct(rs_parent)} relative to {item['parent_sector']} over 20 days."
            ),
        })

    factors = snapshot.get("signal_snapshot", {}).get("factors", {})
    factor_labels = set(snapshot.get("factor_leadership_state", []))
    for symbol, item in factors.items():
        dd20 = float(item.get("drawdown_20d", 0.0))
        rs20 = float(item.get("relative_strength_20d_vs_spy", 0.0))
        if dd20 > -0.03 and rs20 > -0.02:
            continue
        factor_items.append({
            "factor": symbol,
            "commentary": f"{symbol} is {_fmt_pct(dd20)} from its 20-day high and {_fmt_pct(rs20)} versus SPY over 20 days.",
        })

    if "MOMENTUM RESET" in factor_labels:
        factor_items.insert(0, {"factor": "MTUM", "commentary": "Momentum leadership is in a material reset relative to the broad market."})
    if "GROWTH RESET" in factor_labels:
        factor_items.insert(0, {"factor": "IWF/IWD", "commentary": "Growth is resetting relative to value, consistent with internal leadership rotation."})

    subsector_items.sort(key=lambda x: abs(float(subsectors["proxies"][x["symbol"]]["drawdown_20d"])), reverse=True)
    sector_items = sector_items[:6]
    subsector_items = subsector_items[:10]
    factor_items = factor_items[:6]

    noteworthy_count = len(sector_items) + len(subsector_items) + len(factor_items)
    if noteworthy_count == 0:
        summary = "No material sector, subsector, or factor dislocation warrants additional commentary today."
    else:
        summary = (
            f"Noteworthy internal market structure is present across {len(sector_items)} sectors, "
            f"{len(subsector_items)} subsector/industry proxies, and {len(factor_items)} factor observations."
        )
    return {
        "summary": summary,
        "sectors": sector_items,
        "subsectors": subsector_items,
        "factors": factor_items,
        "noteworthy_count": noteworthy_count,
        "commentary_policy": "Only conditions crossing material damage, relative-strength, or repair thresholds are surfaced.",
    }


def enrich_snapshot_with_subsectors(
    snapshot: dict[str, Any],
    require_same_day: bool = True,
    prices: pd.DataFrame | None = None,
) -> dict[str, Any]:
    target = pd.Timestamp(snapshot["as_of"]).normalize()
    prices = load_subsector_prices() if prices is None else prices
    frame = build_subsector_frame(prices)
    if target not in frame.index:
        raise RuntimeError(f"Subsector intelligence unavailable for {target.date()}")

    row = frame.loc[target]
    expected = len(SUBSECTOR_SYMBOLS)
    available = sum(
        1 for s in SUBSECTOR_SYMBOLS if f"sub_{s}_dd20" in row.index and pd.notna(row[f"sub_{s}_dd20"])
    )
    coverage = available / expected if expected else 0.0
    if require_same_day and coverage < 0.90:
        raise RuntimeError(
            f"Same-day subsector coverage below 90%: {available}/{expected} ({coverage:.1%})"
        )

    subsectors = subsector_snapshot(row)
    subsectors["coverage"] = {
        "available_proxies": available,
        "expected_proxies": expected,
        "coverage_rate": coverage,
        "same_day_target": str(target.date()),
    }
    snapshot["subsector_intelligence"] = subsectors
    snapshot["market_commentary"] = build_market_commentary(snapshot, subsectors)
    snapshot.setdefault("implementation", {})["subsector_universe"] = SUBSECTOR_GROUPS
    snapshot["implementation"]["subsector_role"] = (
        "diagnostic market-state and commentary layer; does not change the validated final RE-ENTRY decision until incremental historical validation supports promotion"
    )
    snapshot.setdefault("caveats", []).append(PROXY_CAVEAT)
    return snapshot
