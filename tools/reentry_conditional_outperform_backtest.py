from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_episode_exit_backtest import build_canonical_signal_history
from reentry_subsector_intelligence import SUBSECTOR_SYMBOLS, build_subsector_frame, load_subsector_prices

COOLDOWN=10
COST=0.001
K=15
MIN_HISTORY=20
EVAL_H=(5,10,15,30,60)
PRED_H=(10,30)
FEATURES=("dd20","ret5","rs20_parent","rs_trend")


def episode_starts(s):
    x=s.eq("RE-ENTER") & ~s.shift(1,fill_value="").eq("RE-ENTER")
    return [pd.Timestamp(d) for d in s.index[x]]

def independent(ds,idx):
    out=[]; last=-10000
    for d in ds:
        if d not in idx: continue
        p=idx.get_loc(d)
        if isinstance(p,(int,np.integer)) and int(p)-last>COOLDOWN:
            out.append(d); last=int(p)
    return out

def frow(sf,d,s):
    ks=[f"sub_{s}_dd20",f"sub_{s}_ret5",f"sub_{s}_rs20_parent",f"sub_{s}_rs60_parent"]
    if any(k not in sf.columns or pd.isna(sf.at[d,k]) for k in ks): return None
    return np.array([sf.at[d,ks[0]],sf.at[d,ks[1]],sf.at[d,ks[2]],sf.at[d,ks[2]]-sf.at[d,ks[3]]],float)

def fret(px,d,s,h):
    if s not in px.columns or d not in px.index:return None
    p=px.index.get_loc(d)
    if not isinstance(p,(int,np.integer)):return None
    a=int(p)+1;b=a+h
    if b>=len(px):return None
    x=px[s].iloc[a];y=px[s].iloc[b]
    if pd.isna(x) or pd.isna(y) or float(x)<=0:return None
    return float(y/x-1-COST)

def summarize(a):
    a=np.asarray([x for x in a if x is not None],float)
    return {"n":int(len(a)),"median":float(np.median(a)) if len(a) else None,"mean":float(np.mean(a)) if len(a) else None,"positive_rate":float(np.mean(a>0)) if len(a) else None}

def predict_for_symbol(px,sf,dates,i,sym):
    cur=frow(sf,dates[i],sym)
    if cur is None:return None
    hist=[]
    for j in range(i):
        d=dates[j]; v=frow(sf,d,sym)
        if v is None: continue
        outs=[]
        valid=True
        for h in PRED_H:
            r=fret(px,d,sym,h); b=fret(px,d,"SPY",h)
            if r is None or b is None:valid=False;break
            outs.append(r-b)
        if valid:hist.append((v,float(np.mean(outs))))
    if len(hist)<MIN_HISTORY:return None
    X=np.vstack([x[0] for x in hist]); y=np.array([x[1] for x in hist])
    mu=X.mean(0); sd=X.std(0); sd[sd==0]=1
    normalized_hist=(X-mu)/sd
    normalized_cur=(cur-mu)/sd
    dist=np.sqrt(((normalized_hist-normalized_cur)**2).mean(axis=1))
    ix=np.argsort(dist)[:min(K,len(hist))]
    neigh=y[ix]
    return {"score":float(np.median(neigh)),"mean_excess":float(np.mean(neigh)),"positive_excess_rate":float(np.mean(neigh>0)),"neighbors":int(len(ix))}

def main():
    base=feature_frame(require_same_day=False)
    sig=build_canonical_signal_history(base)["signal"]
    px=load_subsector_prices(start="2016-09-01").sort_index(); sf=build_subsector_frame(px)
    dates=independent([d for d in episode_starts(sig) if d in sf.index],px.index)
    selections=[]
    for i,d in enumerate(dates):
        ranked=[]
        for s in SUBSECTOR_SYMBOLS:
            p=predict_for_symbol(px,sf,dates,i,s)
            if p is not None: ranked.append((s,p))
        ranked.sort(key=lambda x:(x[1]["score"],x[1]["positive_excess_rate"]),reverse=True)
        if len(ranked)>=3: selections.append((d,ranked[:3]))
    res={"eligible_episodes":len(selections),"methodology":{"selector":"per-symbol kNN on prior RE-ENTER episodes only","features":list(FEATURES),"neighbors":K,"minimum_prior_history":MIN_HISTORY,"prediction_target":"mean of 10D and 30D excess return vs SPY","execution":"next-session close","cost":COST},"horizons":{}}
    for h in EVAL_H:
        p1=[];p3=[];spy=[];qqq=[];smh=[];bspy=[];bqqq=[];bsmh=[]
        for d,ranks in selections:
            syms=[x[0] for x in ranks]
            vals=[fret(px,d,s,h) for s in syms];vals=[x for x in vals if x is not None]
            a=vals[0] if vals else None; basket=float(np.mean(vals)) if vals else None
            s=fret(px,d,"SPY",h);q=fret(px,d,"QQQ",h);m=fret(px,d,"SMH",h)
            p1.append(a);p3.append(basket);spy.append(s);qqq.append(q);smh.append(m)
            if basket is not None and s is not None:bspy.append(basket>s)
            if basket is not None and q is not None:bqqq.append(basket>q)
            if basket is not None and m is not None:bsmh.append(basket>m)
        res["horizons"][str(h)]={"top1":summarize(p1),"top3":summarize(p3),"SPY":summarize(spy),"QQQ":summarize(qqq),"SMH_static":summarize(smh),"top3_beat_SPY_rate":float(np.mean(bspy)) if bspy else None,"top3_beat_QQQ_rate":float(np.mean(bqqq)) if bqqq else None,"top3_beat_SMH_rate":float(np.mean(bsmh)) if bsmh else None}
    if selections:
        d,r=selections[-1]
        res["latest_eligible"]={"date":str(d.date()),"top3":[{"symbol":s,**p} for s,p in r]}
    out=Path("artifacts/reentry_conditional_outperform");out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(res,indent=2),encoding="utf-8")
    print(json.dumps(res,indent=2))

if __name__=="__main__":main()
