#!/usr/bin/env python3
"""Broader robustness check for initial intraday feature survivors.

Uses Yahoo 60-minute history over two years. To avoid look-ahead, snapshot values use the
OPEN of each hourly bar, which is known at the bar timestamp. This is coarser than the 5-minute
research pass and is used only as a directional robustness test.
"""
from __future__ import annotations

import json, math, statistics, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "web/public/reentry/validation/historical_episode_ledger_2026-09-09.json"
OUT = ROOT / "research/intraday_signal_robustness.json"
OUT_MD = ROOT / "research/intraday_signal_robustness.md"
GROUPS = {
  "sectors": ["XLC","XLY","XLP","XLE","XLF","XLV","XLI","XLB","XLRE","XLK","XLU"],
  "subsectors": ["FDN","IYZ","PBS","XRT","ITB","PEJ","PBJ","RHS","XOP","OIH","CRAK","KRE","KBE","IAI","KIE","XBI","IBB","IHI","IHF","ITA","XTN","PAVE","XME","COPX","SLX","REZ","SRVR","NETL","SMH","IGV","HACK","RNRG","RYU"],
  "volatility": ["^VIX"],
}
ALL = list(dict.fromkeys(sum(GROUPS.values(), [])))
SNAPS = ["10:30","11:30","13:30","14:30"]


def mean(xs):
    xs=[x for x in xs if isinstance(x,(int,float)) and math.isfinite(x)]
    return sum(xs)/len(xs) if xs else None

def pos(xs):
    xs=[x for x in xs if isinstance(x,(int,float)) and math.isfinite(x)]
    return sum(x>0 for x in xs)/len(xs) if xs else None

def median(xs):
    xs=[x for x in xs if isinstance(x,(int,float)) and math.isfinite(x)]
    return statistics.median(xs) if xs else None

def chart(symbol, interval, range_):
    q=urllib.parse.quote(symbol,safe="")
    url=f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?interval={interval}&range={range_}&includePrePost=false&events=div%2Csplits"
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0 RE-ENTRY-robustness/1.0","Accept":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as r: body=json.loads(r.read().decode())
    result=body.get("chart",{}).get("result",[None])[0]
    if not result: raise RuntimeError(f"{symbol}: no result")
    ts=result.get("timestamp") or []
    quote=((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens=quote.get("open") or []; closes=quote.get("close") or []
    out=[]
    for i,t in enumerate(ts):
        o=opens[i] if i<len(opens) else None; c=closes[i] if i<len(closes) else None
        if isinstance(o,(int,float)) and math.isfinite(o): out.append({"ts":int(t),"open":float(o),"close":float(c) if isinstance(c,(int,float)) else None})
    return out

def by_date(rows):
    out={}
    for r in rows:
        dt=datetime.fromtimestamp(r["ts"],timezone.utc).astimezone(ET)
        if dt.hour<9 or dt.hour>=16: continue
        out.setdefault(dt.date().isoformat(),[]).append({**r,"dt":dt})
    for x in out.values(): x.sort(key=lambda z:z["ts"])
    return out

def prior_close(days,d):
    ks=sorted(k for k in days if k<d)
    if not ks:return None
    vals=[r.get("close") for r in days[ks[-1]] if isinstance(r.get("close"),(int,float))]
    return vals[-1] if vals else None

def bar_open(days,d,hhmm):
    h,m=map(int,hhmm.split(":"))
    rows=days.get(d,[])
    exact=[r for r in rows if (r["dt"].hour,r["dt"].minute)==(h,m)]
    if exact:return exact[0]["open"]
    earlier=[r for r in rows if (r["dt"].hour,r["dt"].minute)<=(h,m)]
    return earlier[-1]["open"] if earlier else None

def daily(symbol):
    rows=chart(symbol,"1d","3y")
    out={}
    for r in rows:
        d=datetime.fromtimestamp(r["ts"],timezone.utc).astimezone(ET).date().isoformat()
        if isinstance(r.get("close"),(int,float)):out[d]=r["close"]
    return out

def future(daily_,d,h):
    ks=sorted(daily_)
    if d not in daily_:return None
    i=ks.index(d); j=i+h
    return daily_[ks[j]]/daily_[d]-1 if j<len(ks) else None

def summary(vals):
    return {"n":len(vals),"mean":mean(vals),"median":median(vals),"positive_rate":pos(vals)}

def main():
    data={}; errors=[]
    for i,s in enumerate(ALL):
        try:data[s]=by_date(chart(s,"60m","2y"))
        except Exception as e:errors.append(f"{s}: {e}")
        if i%10==9:time.sleep(.5)
    spy=daily("SPY"); qqq=daily("QQQ")
    ledger=json.loads(LEDGER.read_text())
    common=sorted(set(data.get("XLC",{})) & set(data.get("SMH",{})))
    if not common:raise SystemExit("No common hourly data")
    lo,hi=common[0],common[-1]
    starts=sorted({e["start"] for e in ledger["episodes"] if lo<=e["start"]<=hi})
    obs=[]
    for d in starts:
        for t in SNAPS:
            moves={}
            for s in ALL:
                days=data.get(s,{})
                p=bar_open(days,d,t); prev=prior_close(days,d)
                if isinstance(p,(int,float)) and isinstance(prev,(int,float)) and prev>0:moves[s]=p/prev-1
            if len(moves)<35:continue
            sec=[moves[s] for s in GROUPS["sectors"] if s in moves]
            sub=[moves[s] for s in GROUPS["subsectors"] if s in moves]
            vix=moves.get("^VIX")
            row={"date":d,"snapshot":t,"sector_positive_share":pos(sec),"subsector_positive_share":pos(sub),"vix_change":vix,"features":{
                "sectors_broad": pos(sec) is not None and pos(sec)>=.55,
                "subsectors_broad": pos(sub) is not None and pos(sub)>=.55,
                "vol_easing": isinstance(vix,(int,float)) and vix<0,
            }}
            for h in (5,10):
                vals=[x for x in (future(spy,d,h),future(qqq,d,h)) if isinstance(x,(int,float))]
                row[f"BROAD_{h}d"]=mean(vals)
            obs.append(row)
    features=["sectors_broad","subsectors_broad","vol_easing"]
    analysis={}
    for f in features:
        analysis[f]={}
        for t in SNAPS:
            rows=[r for r in obs if r["snapshot"]==t]
            analysis[f][t]={}
            for h in (5,10):
                yes=[r[f"BROAD_{h}d"] for r in rows if r["features"][f] and isinstance(r.get(f"BROAD_{h}d"),(int,float))]
                no=[r[f"BROAD_{h}d"] for r in rows if not r["features"][f] and isinstance(r.get(f"BROAD_{h}d"),(int,float))]
                analysis[f][t][str(h)]={"present":summary(yes),"absent":summary(no)}
    robust=[]
    for f in features:
        good=0
        for t in SNAPS:
            a5=analysis[f][t]["5"];a10=analysis[f][t]["10"]
            p5,n5=a5["present"],a5["absent"];p10,n10=a10["present"],a10["absent"]
            ok=min(p5["n"],n5["n"],p10["n"],n10["n"])>=10 and p5["mean"] is not None and n5["mean"] is not None and p10["mean"] is not None and n10["mean"] is not None and p5["mean"]>n5["mean"] and p10["mean"]>n10["mean"]
            good+=int(ok)
        if good>=3:robust.append({"feature":f,"supporting_snapshots":good})
    payload={"generated_at":datetime.now(timezone.utc).isoformat(),"classification":"RESEARCH_ONLY_NON_CANONICAL","engine_impact":"NONE","method":"60-minute Yahoo history; snapshot uses hourly bar OPEN to avoid look-ahead","window":{"start":lo,"end":hi,"episode_starts":len(starts)},"robust_survivors":robust,"analysis":analysis,"errors":errors}
    OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(payload,indent=2,sort_keys=True))
    lines=["# Intraday survivor robustness check","",f"Window: **{lo} through {hi}**, **{len(starts)} reconstructed RE-ENTRY starts**.","","Hourly-bar **opens** are used at each timestamp so the test does not use information from later inside the hour.","","## Robust survivors",""]
    if robust:
        lines += [f"- **{x['feature']}** - higher mean broad-market 5D and 10D forward returns at {x['supporting_snapshots']} of {len(SNAPS)} hourly snapshots, with at least 10 observations on each side." for x in robust]
    else:lines.append("- **None.** The initial 60-day findings did not survive the broader hourly robustness screen.")
    lines += ["","## Snapshot detail",""]
    for f in features:
        lines.append(f"### {f}")
        for t in SNAPS:
            a=analysis[f][t]
            p5,n5=a['5']['present'],a['5']['absent'];p10,n10=a['10']['present'],a['10']['absent']
            def fp(x):return '-' if x is None else f"{x*100:+.2f}%"
            lines.append(f"- {t}: 5D present n={p5['n']} mean {fp(p5['mean'])} vs absent n={n5['n']} {fp(n5['mean'])}; 10D present n={p10['n']} {fp(p10['mean'])} vs absent n={n10['n']} {fp(n10['mean'])}")
        lines.append("")
    lines += ["## Important limitation","","This is a robustness screen on reconstructed episode dates and mutable vendor history. It is not sufficient by itself to promote an intraday feature into the frozen official RE-ENTRY engine."]
    OUT_MD.write_text("\n".join(lines)+"\n")
    print(json.dumps({"window":payload["window"],"robust_survivors":robust,"errors":errors},indent=2))
if __name__=="__main__":main()
