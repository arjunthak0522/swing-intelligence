from __future__ import annotations

# Audited industry/subindustry proxy map for RE-ENTRY research and live diagnostics.
# The primary universe is intentionally not one ETF per sector: weak or artificial
# proxies are omitted rather than counted as if they were true subsectors.
SUBSECTOR_GROUPS: dict[str, list[tuple[str, str]]] = {
    "XLC": [("FDN", "Internet"), ("IYZ", "Telecom"), ("PBS", "Media")],
    "XLY": [("XRT", "Retail"), ("ITB", "Homebuilders"), ("PEJ", "Leisure & Entertainment")],
    "XLP": [("PBJ", "Food & Beverage")],
    "XLE": [("XOP", "Oil & Gas Exploration/Production"), ("OIH", "Oil Services"), ("CRAK", "Refiners")],
    "XLF": [("KRE", "Regional Banks"), ("KBE", "Banks"), ("IAI", "Broker-Dealers"), ("KIE", "Insurance")],
    "XLV": [("XBI", "Biotech"), ("IBB", "Large-Cap Biotech"), ("IHI", "Medical Devices"), ("IHF", "Healthcare Providers")],
    "XLI": [("ITA", "Aerospace & Defense"), ("XTN", "Transportation"), ("PAVE", "U.S. Infrastructure Theme")],
    "XLB": [("XME", "Metals & Mining"), ("COPX", "Copper Miners"), ("SLX", "Steel")],
    "XLRE": [("REZ", "Residential & Specialized REITs"), ("SRVR", "Digital Infrastructure REITs"), ("NETL", "Net Lease REITs")],
    "XLK": [("SMH", "Semiconductors"), ("IGV", "Software"), ("CIBR", "Cybersecurity")],
    "XLU": [("RNRG", "Renewable Power Producers")],
}

# Supporting ETFs are observed but excluded from aggregate subsector breadth so a
# duplicated theme or weighting methodology cannot distort the state calculation.
SUPPORTING_PROXIES: dict[str, dict[str, str]] = {
    "BUG": {
        "label": "Cybersecurity pure-play confirmer",
        "parent": "XLK",
        "role": "live_purity_confirmer",
        "primary_for": "CIBR",
    },
    "HACK": {
        "label": "Cybersecurity long-history comparator",
        "parent": "XLK",
        "role": "historical_comparator",
        "primary_for": "CIBR",
    },
    "RHS": {
        "label": "Equal-Weight Consumer Staples breadth diagnostic",
        "parent": "XLP",
        "role": "weighting_diagnostic_not_subsector",
        "primary_for": "",
    },
    "RYU": {
        "label": "Equal-Weight Utilities breadth diagnostic",
        "parent": "XLU",
        "role": "weighting_diagnostic_not_subsector",
        "primary_for": "",
    },
}

SUBSECTOR_SYMBOLS = [s for groups in SUBSECTOR_GROUPS.values() for s, _ in groups]
PARENT_BY_SYMBOL = {s: parent for parent, groups in SUBSECTOR_GROUPS.items() for s, _ in groups}
LABEL_BY_SYMBOL = {s: label for groups in SUBSECTOR_GROUPS.values() for s, label in groups}

AUDIT_NOTES = {
    "CIBR": "Primary cybersecurity backtest proxy: inception 2015 gives full 2016+ model history and high liquidity.",
    "BUG": "Pure-play cybersecurity confirmer; newer 2019 inception means it is not used as the sole historical proxy.",
    "HACK": "Retained only as a comparator; broader holdings can include networking, semiconductors and defense exposure.",
    "RHS": "Removed from subsector breadth because equal-weighting is a construction method, not an industry/subindustry.",
    "RYU": "Removed from subsector breadth because equal-weighting is a construction method, not an industry/subindustry.",
    "PAVE": "Kept but explicitly labeled a cross-industry U.S. infrastructure theme rather than a pure GICS subsector.",
    "SRVR": "Relabeled Digital Infrastructure REITs to reflect towers/connectivity/data-center exposure more accurately.",
    "RNRG": "Kept as a renewable power producer proxy; it is global and thematic, so interpretation should remain contextual.",
}
