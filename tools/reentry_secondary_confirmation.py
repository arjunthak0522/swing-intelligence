#!/usr/bin/env python3
from __future__ import annotations

import argparse, csv, html, json, math, re
from datetime import datetime
from io import StringIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")
CBOE_HISTORY = "https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
T2108_BATCH_SIZE = 180


def finite(v):
    try: return v is not None and math.isfinite(float(v))
    except Exception: return False


def ticker_close(frame: pd.DataFrame, ticker: str) -> pd.Series:
    if frame.empty: return pd.Series(dtype=float)
    if isinstance(frame.columns, pd.MultiIndex):
        for getter in (lambda: frame["Close"][ticker], lambda: frame[ticker]["Close"]):
            try: return pd.to_numeric(getter(), errors="coerce").dropna()
            except Exception: pass
        return pd.Series(dtype=float)
    return pd.to_numeric(frame["Close"], errors="coerce").dropna() if "Close" in frame.columns else pd.Series(dtype=float)


def pct_change(s: pd.Series, n=5):
    if len(s) <= n: return None
    a,b=float(s.iloc[-1]),float(s.iloc[-1-n]); return a/b-1 if b else None


def cboe_close(symbol: str) -> pd.Series:
    url=CBOE_HISTORY.format(symbol=symbol)
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 RE-ENTRY/1.0","Accept":"text/csv,*/*"})
    with urlopen(req,timeout=20) as resp: raw=resp.read().decode("utf-8",errors="replace")
    df=pd.read_csv(StringIO(raw))
    cols={c.upper().strip():c for c in df.columns}
    date_col=cols.get("DATE"); close_col=cols.get("CLOSE") or cols.get(symbol.upper())
    if not date_col or not close_col: raise ValueError(f"Unexpected Cboe {symbol} columns: {list(df.columns)}")
    dates=pd.to_datetime(df[date_col],errors="coerce"); vals=pd.to_numeric(df[close_col],errors="coerce")
    s=pd.Series(vals.values,index=dates).dropna(); s=s[~s.index.isna()].sort_index()
    if s.empty: raise ValueError(f"Cboe {symbol} history empty")
    return s


def vix_term_structure(market_date: str|None):
    vix,vix3m=cboe_close("VIX"),cboe_close("VIX3M")
    aligned=pd.concat([vix.rename("VIX"),vix3m.rename("VIX3M")],axis=1,sort=True).dropna()
    if market_date: aligned=aligned.loc[aligned.index<=pd.Timestamp(market_date)]
    if len(aligned)<2: raise ValueError("Insufficient official VIX/VIX3M history")
    ratio=aligned.VIX/aligned.VIX3M; cur,prior=float(ratio.iloc[-1]),float(ratio.iloc[-2]); last=ratio.index[-1].date().isoformat()
    state="ACUTE_STRESS" if cur>1.10 else "BACKWARDATION" if cur>1 else "NORMALIZING" if prior>1 and cur<=1 else "NORMALIZED" if cur<=.97 else "NEAR_NORMAL"
    return {"name":"VIX term-structure repair","state":state,"supportive":cur<=1 or (prior>1 and cur<prior),"current_ratio":cur,"prior_ratio":prior,"change":cur-prior,"normalization_cross":prior>1 and cur<=1,"benchmark":">1.10 acute inversion · >1.00 backwardation/stress · cross below 1.00 normalization · <0.97 normalized contango","retail_explanation":"This asks whether near-term market fear is still unusually intense or starting to calm down. A move back below 1.00 is generally healthier for a rebound.","signal_behavior":"CONFIRMING","behavior_explanation":"This is mainly a confirmation signal: falling below 1.00 shows short-term volatility stress is normalizing. A high ratio itself is not bullish; the repair is what matters.","freshness_type":"DAILY_CLOSE","last_updated":last,"source":"Cboe official daily VIX and VIX3M history","validation_status":"VALIDATED_EVENT_SUPPORT","validation_note":"Frozen 2007-2026 falsification: QQQ 10D after VIX/VIX3M normalization below 1.00, n=78, median +2.17%, positive 69.2%, matched excess +1.17%; workflow run 33811926596."}


def breadth_thrust(values, stamp):
    adv,dec=values.get("NAADV"),values.get("NADEC"); total=float(adv)+float(dec) if finite(adv) and finite(dec) else None; r=float(adv)/total if total and total>0 else None
    state,supportive=("UNAVAILABLE",False) if r is None else ("THRUST_LEVEL",True) if r>=.615 else ("BUILDING",True) if r>=.55 else ("MIXED",False) if r>=.45 else ("DEFENSIVE",False)
    return {"name":"Breadth participation thrust","state":state,"supportive":supportive,"nasdaq_advance_share":r,"advancing_issues":float(adv) if finite(adv) else None,"declining_issues":float(dec) if finite(dec) else None,"benchmark":"<45% defensive · 45-55% mixed · 55-61.5% building · >=61.5% strong thrust-level participation","retail_explanation":"This checks whether the rebound is spreading across lots of stocks instead of being carried by just a few big names.","signal_behavior":"CONFIRMING","behavior_explanation":"Higher participation confirms that a rebound is broad rather than narrow.","freshness_type":"INTRADAY_SNAPSHOT","last_updated":stamp,"source":"Current Nasdaq advancing/declining issues captured by RE-ENTRY","validation_status":"LIMITED_HISTORY_CONTEXT_ONLY","validation_note":"Exact Nasdaq advance/decline history through February 2020 covered 18 historical DEPLOY episodes. None had >=55% advance share at the DEPLOY start; waiting for that participation threshold took a median 1 session and cost a median +0.65% SPY / +0.58% QQQ. Keep as research/context only; exact history does not cover 2020-2026."}


def download_one(ticker):
    return ticker_close(yf.download(ticker,period="2mo",interval="1d",auto_adjust=True,progress=False,threads=False,timeout=20),ticker)


def risk_appetite():
    tickers=["RSP","SPY","IWM","HYG","LQD"]; px={t:download_one(t) for t in tickers}; common=None
    for s in px.values(): common=s.index if common is None else common.intersection(s.index)
    if common is None or len(common)<7: raise ValueError("Insufficient risk-appetite history")
    def rel(a,b):
        r=(px[a].reindex(common)/px[b].reindex(common)).dropna(); return float(r.iloc[-1]),pct_change(r,5)
    rsp,rsp5=rel("RSP","SPY"); iwm,iwm5=rel("IWM","SPY"); hyg,hyg5=rel("HYG","LQD")
    comps={"equal_weight_broadening":bool(rsp5 is not None and rsp5>0),"small_caps_confirming":bool(iwm5 is not None and iwm5>0),"credit_risk_appetite":bool(hyg5 is not None and hyg5>0)}; n=sum(comps.values())
    return {"name":"Risk-appetite broadening","state":["DEFENSIVE","MIXED","BROADENING","BROAD_RISK_ON"][n],"supportive":n>=2,"supportive_components":n,"components":comps,"RSP_SPY":rsp,"RSP_SPY_5d_change":rsp5,"IWM_SPY":iwm,"IWM_SPY_5d_change":iwm5,"HYG_LQD":hyg,"HYG_LQD_5d_change":hyg5,"benchmark":"0/3 defensive · 1/3 mixed · 2/3 broadening · 3/3 broad risk-on; positive 5-session relative momentum required","retail_explanation":"This checks whether investors are moving beyond the biggest stocks into equal-weight stocks, small caps, and lower-quality credit.","signal_behavior":"CONFIRMING","behavior_explanation":"Broadening into smaller stocks and credit confirms that investors are becoming more willing to take risk.","freshness_type":"DAILY_CLOSE","last_updated":pd.Timestamp(common[-1]).date().isoformat(),"source":"Yahoo Finance daily adjusted closes: RSP/SPY, IWM/SPY, HYG/LQD","validation_status":"VALIDATED_CONTEXT_ONLY","validation_note":"Across 94 historical DEPLOY episodes, the 2-of-3 risk-appetite composite was supportive at 36 starts and failed every SPY/QQQ 10D/30D incremental quality gate versus all DEPLOY episodes. It is low-redundancy context (correlation with existing B50 proxy about 0.10), but it does not improve the entry rule or recovery-stage classification."}


def cboe_put_call(market_date):
    url=f"https://www.cboe.com/markets/us/options/market-statistics/daily?{urlencode({'dt':market_date})}"; req=Request(url,headers={"User-Agent":"Mozilla/5.0 RE-ENTRY/1.0"})
    with urlopen(req,timeout=25) as resp: raw=resp.read().decode("utf-8",errors="replace")
    text=re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",raw)))
    def extract(label):
        m=re.search(re.escape(label)+r"\s*([0-9]+(?:\.[0-9]+)?)",text,re.I); return float(m.group(1)) if m else None
    eq,idx,total=extract("EQUITY PUT/CALL RATIO"),extract("INDEX PUT/CALL RATIO"),extract("TOTAL PUT/CALL RATIO")
    if eq is None and idx is None: raise ValueError("Cboe page did not expose put/call ratios")
    state="UNAVAILABLE" if eq is None else "HIGH_FEAR" if eq>=.9 else "FEAR" if eq>=.7 else "NORMAL" if eq>=.5 else "COMPLACENT"
    return {"name":"Options sentiment","state":state,"supportive":False,"equity_put_call":eq,"index_put_call":idx,"total_put_call":total,"benchmark":"Equity P/C <0.50 complacent · 0.50-0.70 normal · 0.70-0.90 fear · >=0.90 high fear (working display scale until percentiles mature)","retail_explanation":"This looks at how heavily traders are using puts versus calls. High put activity often means fear is elevated.","signal_behavior":"CONTRARIAN","behavior_explanation":"Unusually high fear can improve a re-entry setup, but fear alone is not a buy signal. Confirmation comes when fear retreats while breadth improves.","freshness_type":"DAILY_CLOSE","last_updated":market_date,"source":"Cboe U.S. Options Daily Market Statistics","validation_status":"VALIDATED_SENTIMENT_OVERLAY","validation_note":"Across 94 historical DEPLOY episodes using Cboe archive plus daily statistics, equity fear (P/C >=0.70) appeared at 49 starts and was generally supportive over 30-90D, but missed the SPY 10D median gate. Fear-reversing occurred at only 14 starts, below the promotion sample threshold. Cboe also documents 2022 early-exercise distortion in raw equity P/C. Keep as a contrarian sentiment overlay, never a DEPLOY gate."}


def nyse_symbols() -> list[str]:
    req=Request(OTHER_LISTED,headers={"User-Agent":"Mozilla/5.0 RE-ENTRY-T2108/1.0"})
    with urlopen(req,timeout=30) as resp: raw=resp.read().decode("utf-8",errors="replace")
    rows=[]
    for row in csv.DictReader(StringIO(raw),delimiter="|"):
        if not row or str(row.get("ACT Symbol","")).startswith("File Creation Time"): continue
        if str(row.get("Exchange","")).strip().upper()!="N": continue
        if str(row.get("ETF","N")).strip().upper()=="Y" or str(row.get("Test Issue","N")).strip().upper()=="Y": continue
        symbol=str(row.get("ACT Symbol","")).strip(); name=str(row.get("Security Name","")).upper()
        if not symbol or any(token in name for token in (" WARRANT"," WTS"," UNIT"," RIGHT"," PREFERRED")): continue
        if not re.fullmatch(r"[A-Z0-9.\-]+",symbol): continue
        rows.append(symbol.replace(".","-"))
    return sorted(set(rows))


def t2108_context(market_date: str|None):
    symbols=nyse_symbols()
    if len(symbols)<500: raise ValueError(f"NYSE universe unexpectedly small: {len(symbols)}")
    current_above=prior_above=current_valid=prior_valid=0
    latest_date=None
    cutoff=pd.Timestamp(market_date) if market_date else None
    for start in range(0,len(symbols),T2108_BATCH_SIZE):
        batch=symbols[start:start+T2108_BATCH_SIZE]
        try:
            frame=yf.download(batch,period="3mo",interval="1d",group_by="ticker",auto_adjust=True,progress=False,threads=True,timeout=25)
        except Exception:
            continue
        for ticker in batch:
            closes=ticker_close(frame,ticker)
            if closes.empty: continue
            closes.index=pd.to_datetime(closes.index)
            if cutoff is not None: closes=closes.loc[closes.index.normalize()<=cutoff.normalize()]
            if len(closes)<40: continue
            latest_date=max(latest_date,closes.index[-1]) if latest_date is not None else closes.index[-1]
            cur=float(closes.iloc[-1]); ma40=float(closes.iloc[-40:].mean())
            if finite(cur) and finite(ma40) and ma40>0:
                current_valid+=1
                if cur>ma40: current_above+=1
            if len(closes)>=41:
                prior=float(closes.iloc[-2]); prior_ma40=float(closes.iloc[-41:-1].mean())
                if finite(prior) and finite(prior_ma40) and prior_ma40>0:
                    prior_valid+=1
                    if prior>prior_ma40: prior_above+=1
    coverage=current_valid/len(symbols) if symbols else 0.0
    if current_valid<600 or coverage<0.35: raise ValueError(f"Insufficient T2108-equivalent coverage: {current_valid}/{len(symbols)} ({coverage:.1%})")
    value=100.0*current_above/current_valid
    prior_value=100.0*prior_above/prior_valid if prior_valid else None
    delta=value-prior_value if prior_value is not None else None
    state="EXTREME_OVERSOLD" if value<10 else "OVERSOLD" if value<20 else "WEAK" if value<40 else "NORMAL" if value<70 else "STRONG" if value<80 else "VERY_EXTENDED"
    direction="RISING" if delta is not None and delta>=1 else "FALLING" if delta is not None and delta<=-1 else "FLAT"
    return {"name":"T2108 breadth context","symbol":"T2108-EQUIVALENT","value":value,"prior_value":prior_value,"change_points":delta,"state":state,"direction":direction,"decision_input":False,"supportive":False,"universe_size":len(symbols),"valid_count":current_valid,"coverage_pct":coverage*100.0,"above_40dma_count":current_above,"benchmark":"<10% extreme oversold · 10-20% oversold · 20-40% weak · 40-70% normal · 70-80% strong · >80% very extended","retail_explanation":"This shows the percentage of NYSE stocks trading above their 40-day moving average. It is an intermediate-speed breadth gauge between very short-term breadth and long-term market structure.","behavior_explanation":"When this falls to deeply oversold levels, it is a contrarian bullish setup for re-entry because weakness is widespread and may be exhausting. A turn higher is the stronger confirmation; the low reading alone does not trigger DEPLOY.","freshness_type":"DAILY_CLOSE","last_updated":pd.Timestamp(latest_date).date().isoformat() if latest_date is not None else market_date,"source":"RE-ENTRY calculated T2108-equivalent from current NYSE-listed non-ETF equities and 40-day adjusted closes","validation_status":"VALIDATED_CONTEXT_ONLY","validation_note":"Incremental validation across 94 DEPLOY episodes found the NYSE 40-day breadth reconstruction highly redundant with existing breadth (correlation about 0.94). Requiring <40% and rising delayed entry by a median 2 sessions and cost median +0.17% SPY / +0.33% QQQ. Keep as breadth context only, not a vote or required confirmation."}


def append_history(path,row):
    path.parent.mkdir(parents=True,exist_ok=True); fields=list(row); rows=[]
    if path.exists():
        with path.open(newline="",encoding="utf-8") as h: reader=csv.DictReader(h); rows=list(reader); fields=list(reader.fieldnames or [])
        for k in row:
            if k not in fields: fields.append(k)
        if rows and rows[-1].get("timestamp_et")==row.get("timestamp_et"): rows[-1]=row
        else: rows.append(row)
    else: rows=[row]
    with path.open("w",newline="",encoding="utf-8") as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)


def main():
    p=argparse.ArgumentParser(); p.add_argument("--snapshot",required=True); p.add_argument("--history",required=True); a=p.parse_args(); snap,hist=Path(a.snapshot),Path(a.history)
    payload=json.loads(snap.read_text()); values=payload.get("values") or {}; unified=payload.get("unified_engine") or {}; date=unified.get("market_date") or values.get("market_date"); stamp=unified.get("timestamp_et") or values.get("timestamp_et") or datetime.now(ET).isoformat()
    builders={"vol_structure":lambda:vix_term_structure(str(date) if date else None),"breadth_thrust":lambda:breadth_thrust(values,stamp),"risk_appetite":risk_appetite,"options_sentiment":lambda:cboe_put_call(str(date))}; families={}; errors={}
    for key,builder in builders.items():
        try: families[key]=builder()
        except Exception as exc: errors[key]=f"{type(exc).__name__}: {exc}"; families[key]={"name":key.replace("_"," ").title(),"state":"UNAVAILABLE","supportive":False,"retail_explanation":"This signal could not be calculated from the current data feed.","signal_behavior":"CONTEXTUAL","behavior_explanation":"No directional interpretation is assigned while unavailable.","freshness_type":"UNAVAILABLE","last_updated":None,"validation_status":"RESEARCH_PENDING","error":errors[key]}
    try:
        t2108=t2108_context(str(date) if date else None)
    except Exception as exc:
        errors["t2108"]=f"{type(exc).__name__}: {exc}"
        t2108={"name":"T2108 breadth context","symbol":"T2108-EQUIVALENT","state":"UNAVAILABLE","direction":"UNAVAILABLE","decision_input":False,"retail_explanation":"The NYSE 40-day breadth context could not be calculated from the current data feed.","behavior_explanation":"No contrarian or confirming interpretation is assigned while unavailable.","freshness_type":"UNAVAILABLE","last_updated":None,"validation_status":"RESEARCH_PENDING","error":errors["t2108"]}
    support=sum(bool(v.get("supportive")) for v in families.values()); overlay={"version":"REENTRY_SECONDARY_CONFIRMATION_v1","timestamp_et":stamp,"market_date":date,"decision_input":False,"changes_deploy_trigger":False,"changes_recovery_stage":False,"supportive_family_count":support,"family_count":len(families),"families":families,"breadth_context":{"t2108":t2108},"errors":errors,"interpretation":"Secondary confirmation describes whether participation, volatility structure, risk appetite, and options sentiment corroborate the existing RE-ENTRY signal. T2108 is separate breadth context and does not change the confirmation score. None of these signals create, block, delay, or revoke DEPLOY."}
    payload["secondary_confirmation"]=overlay
    payload["t2108_context"]=t2108
    payload.setdefault("values",{})["T2108"]=t2108.get("value")
    if unified: unified["secondary_confirmation"]=overlay; payload["unified_engine"]=unified
    snap.write_text(json.dumps(payload,indent=2)+"\n")
    row={"market_date":date,"timestamp_et":stamp,"deployment_signal":unified.get("deployment_signal"),"market_condition":unified.get("market_condition"),"recovery_stage":unified.get("recovery_stage"),"supportive_family_count":support,"t2108_value":t2108.get("value"),"t2108_state":t2108.get("state"),"t2108_direction":t2108.get("direction"),"t2108_coverage_pct":t2108.get("coverage_pct")}
    for key,f in families.items(): row[f"{key}_state"]=f.get("state"); row[f"{key}_supportive"]=f.get("supportive"); row[f"{key}_last_updated"]=f.get("last_updated")
    append_history(hist,row); print(json.dumps(overlay,indent=2))

if __name__=="__main__": main()
