# Intraday state-transition validation

Target: **Will RE-ENTRY still be active at the completed close, or will the state change?**

Window: **2024-09-09 through 2026-09-09**, 334 labeled trading days from reconstructed episodes.

The test uses hourly-bar opens, so no later-in-the-hour price is used at a snapshot.

## Risk score

One point each for: broad SPY/QQQ move below zero, sector+subsector breadth below 50%, and VIX above the prior close.

### 10:30 ET
- Base state-change rate: **25.9%** (n=332)
- Risk score 2-3: **30.9%** state-change rate (n=149)
- Risk score 0-1: **21.9%** state-change rate (n=183)

### 11:30 ET
- Base state-change rate: **25.9%** (n=332)
- Risk score 2-3: **32.5%** state-change rate (n=151)
- Risk score 0-1: **20.4%** state-change rate (n=181)

### 13:30 ET
- Base state-change rate: **25.8%** (n=333)
- Risk score 2-3: **30.1%** state-change rate (n=146)
- Risk score 0-1: **22.5%** state-change rate (n=187)

### 14:30 ET
- Base state-change rate: **25.8%** (n=333)
- Risk score 2-3: **27.3%** state-change rate (n=143)
- Risk score 0-1: **24.7%** state-change rate (n=190)

## Interpretation

This test is aimed at making the intraday panel useful as an early **state-quality / deterioration warning**, not as a second official trading engine. Any production wording should remain provisional until the completed close.

## Limitation

Labels are reconstructed from the continuous episode ledger and hourly data is vendor-adjustable. This is evidence for UI context, not a change to the frozen official signal policy.
