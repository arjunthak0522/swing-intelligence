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
    return {"name":"Breadth participation thrust","state":state,"supportive":supportive,"nasdaq_advance_share":r,"advancing_issues":float(adv) if finite(adv) else None,"declining_issues":float(dec) if finite(dec) else None,"benchmark":"<45% defensive · 45-55% mixed · 55-61.5% building · >=61.5% strong thrust-level participation","retail_explanation":"This checks whether the rebound is spreading across lots of stocks instead of being carried by just a few big names.","signal_behavior":"CONFIRMING","behavior_explanation":"Higher participation confirms that a rebound is broad rather than narrow.","freshness_type":"INTRADAY_SNAPSHOT","last_updated":stamp,"source":"Current Nasdaq advancing/declining issues captured by RE-ENTRY","validation_status":"RESEARCH_PENDING","validation_note":"61.5% is a classic thrust reference; a true Zweig signal also requires a move from below 40% within 10 sessions."}


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
    return {"name":"Risk-appetite broadening","state":["DEFENSIVE","MIXED","BROADENING","BROAD_RISK_ON"][n],"supportive":n>=2,"supportive_components":n,"components":comps,"RSP_SPY":rsp,"RSP_SPY_5d_change":rsp5,"IWM_SPY":iwm,"IWM_SPY_5d_change":iwm5,"HYG_LQD":hyg,"HYG_LQD_5d_change":hyg5,"benchmark":"0/3 defensive · 1/3 mixed · 2/3 broadening · 3/3 broad risk-on; positive 5-session relative momentum required","retail_explanation":"This checks whether investors are moving beyond the biggest stocks into equal-weight stocks, small caps, and lower-quality credit.","signal_behavior":"CONFIRMING","behavior_explanation":"Broadening into smaller stocks and credit confirms that investors are becoming more willing to take risk.","freshness_type":"DAILY_CLOSE","last_updated":pd.Timestamp(common[-1]).date().isoformat(),"source":"Yahoo Finance daily adjusted closes: RSP/SPY, IWM/SPY, HYG/LQD","validation_status":"RESEARCH_PENDING","validation_note":"Composite is one family, not three votes; historical conditional validation is required before promotion."}


def cboe_put_call(market_date):
    url=f"https://www.cboe.com/markets/us/options/market-statistics/daily?{urlencode({'dt':market_date})}"; req=Request(url,headers={"User-Agent":"Mozilla/5.0 RE-ENTRY/1.0"})
    with urlopen(req,timeout=25) as resp: raw=resp.read().decode("utf-8",errors="replace")
    text=re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",raw)))
    def extract(label):
        m=re.search(re.escape(label)+r"\s*([0-9]+(?:\.[0-9]+)?)",text,re.I); return float(m.group(1)) if m else None
    eq,idx,total=extract("EQUITY PUT/CALL RATIO"),extract("INDEX PUT/CALL RATIO"),extract("TOTAL PUT/CALL RATIO")
    if eq is None and idx is None: raise ValueError("Cboe page did not expose put/call ratios")
    state="UNAVAILABLE" if eq is None else "HIGH_FEAR" if eq>=.9 else "FEAR" if eq>=.7 else "NORMAL" if eq>=.5 else "COMPLACENT"
    return {"name":"Options sentiment","state":state,"supportive":False,"equity_put_call":eq,"index_put_call":idx,"total_put_call":total,"benchmark":"Equity P/C <0.50 complacent · 0.50-0.70 normal · 0.70-0.90 fear · >=0.90 high fear (working display scale until percentiles mature)","retail_explanation":"This looks at how heavily traders are using puts versus calls. High put activity often means fear is elevated.","signal_behavior":"CONTRARIAN","behavior_explanation":"Unusually high fear can improve a re-entry setup, but fear alone is not a buy signal. Confirmation comes when fear retreats while breadth improves.","freshness_type":"DAILY_CLOSE","last_updated":market_date,"source":"Cboe U.S. Options Daily Market Statistics","validation_status":"RESEARCH_PENDING","validation_note":"Equity and index ratios remain separate; this family cannot veto DEPLOY."}


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
    support=sum(bool(v.get("supportive")) for v in families.values()); overlay={"version":"REENTRY_SECONDARY_CONFIRMATION_v1","timestamp_et":stamp,"market_date":date,"decision_input":False,"changes_deploy_trigger":False,"changes_recovery_stage":False,"supportive_family_count":support,"family_count":len(families),"families":families,"errors":errors,"interpretation":"Secondary confirmation describes whether participation, volatility structure, risk appetite, and options sentiment corroborate the existing RE-ENTRY signal. It does not create, block, delay, or revoke DEPLOY."}
    payload["secondary_confirmation"]=overlay
    if unified: unified["secondary_confirmation"]=overlay; payload["unified_engine"]=unified
    snap.write_text(json.dumps(payload,indent=2)+"\n")
    row={"market_date":date,"timestamp_et":stamp,"deployment_signal":unified.get("deployment_signal"),"market_condition":unified.get("market_condition"),"recovery_stage":unified.get("recovery_stage"),"supportive_family_count":support}
    for key,f in families.items(): row[f"{key}_state"]=f.get("state"); row[f"{key}_supportive"]=f.get("supportive"); row[f"{key}_last_updated"]=f.get("last_updated")
    append_history(hist,row); print(json.dumps(overlay,indent=2))

if __name__=="__main__": main()
