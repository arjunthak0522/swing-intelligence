#!/usr/bin/env python3
"""Test whether intraday market state helps anticipate the completed-close RE-ENTRY state.

Research only. Uses reconstructed continuous RE-ENTRY episodes and hourly-bar opens to avoid
look-ahead. The target is not future return. The target is whether a day closes with RE-ENTRY
still active versus a transition to WAIT / NO RE-ENTRY SETUP.
"""
from __future__ import annotations
import json, math, statistics, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET=ZoneInfo("America/New_York")
ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"web/public/reentry/validation/historical_episode_ledger_2026-09-09.json"
OUT=ROOT/"research/intraday_state_transition_validation.json"
OUT_MD=ROOT/"research/intraday_state_transition_validation.md"
SECTORS=["XLC","XLY","XLP","XLE","XLF","XLV","XLI","XLB","XLRE","XLK","XLU"]
SUBS=["FDN","IYZ","PBS","XRT","ITB","PEJ","PBJ","RHS","XOP","OIH","CRAK","KRE","KBE","IAI","KIE","XBI","IBB","IHI","IHF","ITA","XTN","PAVE","XME","COPX","SLX","REZ","SRVR","NETL","SMH","IGV","HACK","RNRG","RYU"]
ALL=["SPY","QQQ","^VIX"]+SECTORS+SUBS
SNAPS=["10:30","11:30","13:30","14:30"]

def mean(xs):
    xs=[x for x in xs if isinstance(x,(int,float)) and math.isfinite(x)]
    return sum(xs)/len(xs) if xs else None

def pos(xs):
    xs=[x for x in xs if isinstance(x,(int,float)) and math.isfinite(x)]
    return sum(x>0 for x in xs)/len(xs) if xs else None

def chart(symbol,interval="60m",range_="2y"):
    q=urllib.parse.quote(symbol,safe="")
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?interval={interval}&range={range_}&includePrePost=false"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 RE-ENTRY-state-research/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as r: body=json.loads(r.read().decode())
    result=body.get("chart",{}).get("result",[None])[0]
    if not result: raise RuntimeError(f"{symbol}: no result")
    ts=result.get("timestamp") or []; qd=((result.get("indicators") or {}).get("quote") or [{}])[0]
    op=qd.get("open") or []; cl=qd.get("close") or []
    rows=[]
    for i,t in enumerate(ts):
        o=op[i] if i<len(op) else None; c=cl[i] if i<len(cl) else None
        if isinstance(o,(int,float)) and math.isfinite(o):rows.append({"ts":int(t),"open":float(o),"close":float(c) if isinstance(c,(int,float)) else None})
    return rows

def by_date(rows):
    out={}
    for r in rows:
        dt=datetime.fromtimestamp(r["ts"],timezone.utc).astimezone(ET)
        if dt.hour<9 or dt.hour>=16:continue
        out.setdefault(dt.date().isoformat(),[]).append({**r,"dt":dt})
    for x in out.values():x.sort(key=lambda r:r["ts"])
    return out

def prior_close(days,d):
    ks=sorted(k for k in days if k<d)
    if not ks:return None
    vals=[r.get("close") for r in days[ks[-1]] if isinstance(r.get("close"),(int,float))]
    return vals[-1] if vals else None

def snap_open(days,d,t):
    h,m=map(int,t.split(":")); rows=days.get(d,[])
    exact=[r for r in rows if (r["dt"].hour,r["dt"].minute)==(h,m)]
    if exact:return exact[0]["open"]
    prior=[r for r in rows if (r["dt"].hour,r["dt"].minute)<=(h,m)]
    return prior[-1]["open"] if prior else None

def rate(rows,key="changed"):
    return sum(bool(r[key]) for r in rows)/len(rows) if rows else None

def stats(vals):
    vals=[v for v in vals if isinstance(v,(int,float)) and math.isfinite(v)]
    return {"n":len(vals),"mean":mean(vals),"median":statistics.median(vals) if vals else None}

def main():
    raw={}; errors=[]
    for i,s in enumerate(ALL):
        try:raw[s]=by_date(chart(s))
        except Exception as e:errors.append(f"{s}: {e}")
        if i%10==9:time.sleep(.5)
    spy_days=raw.get("SPY",{})
    trading=sorted(spy_days)
    if not trading:raise SystemExit("No SPY hourly history")
    lo,hi=trading[0],trading[-1]
    ledger=json.loads(LEDGER.read_text())
    labels={}
    for e in ledger["episodes"]:
        s=e["start"]; end=e.get("favorable_through"); trans=e.get("next_state_date")
        if not end:continue
        for d in trading:
            if s<=d<=end:labels[d]="REENTER_HOLDS"
        if trans and lo<=trans<=hi:labels[trans]="STATE_CHANGES"
    observations=[]
    for d,label in sorted(labels.items()):
        if not (lo<=d<=hi):continue
        for t in SNAPS:
            moves={}
            for s in ALL:
                days=raw.get(s,{})
                p=snap_open(days,d,t); prev=prior_close(days,d)
                if isinstance(p,(int,float)) and isinstance(prev,(int,float)) and prev>0:moves[s]=p/prev-1
            if len(moves)<35:continue
            broad=mean([moves.get("SPY"),moves.get("QQQ")])
            sec=pos([moves.get(s) for s in SECTORS])
            sub=pos([moves.get(s) for s in SUBS])
            breadth=mean([sec,sub]); vix=moves.get("^VIX")
            risks={
                "broad_negative": isinstance(broad,(int,float)) and broad<0,
                "breadth_below_half": isinstance(breadth,(int,float)) and breadth<.50,
                "vix_up": isinstance(vix,(int,float)) and vix>0,
            }
            risk_score=sum(risks.values())
            observations.append({"date":d,"snapshot":t,"label":label,"changed":label=="STATE_CHANGES","broad_move":broad,"breadth_positive_share":breadth,"vix_change":vix,"risks":risks,"risk_score":risk_score})
    analysis={}
    for t in SNAPS:
        rows=[r for r in observations if r["snapshot"]==t]
        hold=[r for r in rows if not r["changed"]]; change=[r for r in rows if r["changed"]]
        score={}
        for s in range(4):
            x=[r for r in rows if r["risk_score"]==s]
            score[str(s)]={"n":len(x),"state_change_rate":rate(x)}
        analysis[t]={
            "n":len(rows),"hold_n":len(hold),"change_n":len(change),"base_change_rate":rate(rows),
            "hold_features":{"broad_move":stats([r["broad_move"] for r in hold]),"breadth_positive_share":stats([r["breadth_positive_share"] for r in hold]),"vix_change":stats([r["vix_change"] for r in hold])},
            "change_features":{"broad_move":stats([r["broad_move"] for r in change]),"breadth_positive_share":stats([r["breadth_positive_share"] for r in change]),"vix_change":stats([r["vix_change"] for r in change])},
            "risk_score":score,
            "risk_2plus":{"n":len([r for r in rows if r["risk_score"]>=2]),"state_change_rate":rate([r for r in rows if r["risk_score"]>=2])},
            "risk_0to1":{"n":len([r for r in rows if r["risk_score"]<2]),"state_change_rate":rate([r for r in rows if r["risk_score"]<2])},
        }
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"classification":"RESEARCH_ONLY_NON_CANONICAL","engine_impact":"NONE","target":"same-day completed-close RE-ENTRY state hold vs state change","window":{"start":lo,"end":hi,"labeled_days":len(labels)},"analysis":analysis,"errors":errors}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,indent=2,sort_keys=True))
    def fp(x):return '-' if x is None else f"{x*100:.1f}%"
    lines=["# Intraday state-transition validation","","Target: **Will RE-ENTRY still be active at the completed close, or will the state change?**","",f"Window: **{lo} through {hi}**, {len(labels)} labeled trading days from reconstructed episodes.","","The test uses hourly-bar opens, so no later-in-the-hour price is used at a snapshot.","","## Risk score","","One point each for: broad SPY/QQQ move below zero, sector+subsector breadth below 50%, and VIX above the prior close.",""]
    for t in SNAPS:
        a=analysis[t]
        lines += [f"### {t} ET",f"- Base state-change rate: **{fp(a['base_change_rate'])}** (n={a['n']})",f"- Risk score 2-3: **{fp(a['risk_2plus']['state_change_rate'])}** state-change rate (n={a['risk_2plus']['n']})",f"- Risk score 0-1: **{fp(a['risk_0to1']['state_change_rate'])}** state-change rate (n={a['risk_0to1']['n']})",""]
    lines += ["## Interpretation","","This test is aimed at making the intraday panel useful as an early **state-quality / deterioration warning**, not as a second official trading engine. Any production wording should remain provisional until the completed close.","","## Limitation","","Labels are reconstructed from the continuous episode ledger and hourly data is vendor-adjustable. This is evidence for UI context, not a change to the frozen official signal policy."]
    OUT_MD.write_text("\n".join(lines)+"\n")
    print(json.dumps({"window":payload["window"],"analysis":analysis,"errors":errors},indent=2))
if __name__=="__main__":main()
