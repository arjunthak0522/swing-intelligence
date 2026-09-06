from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from reentry_confidence import feature_frame
from reentry_episode_exit_backtest import build_canonical_signal_history
from reentry_outperform_ranking import rank_subsector_outperformance
from reentry_subsector_intelligence import build_subsector_frame, load_subsector_prices

HORIZONS = (5, 10, 15, 30, 60)
COST = 0.001
COOLDOWN = 10


def starts(signals: pd.Series) -> list[pd.Timestamp]:
    flag = signals.eq("RE-ENTER") & ~signals.shift(1, fill_value="").eq("RE-ENTER")
    return [pd.Timestamp(x) for x in signals.index[flag]]


def independent(ds: list[pd.Timestamp], idx: pd.Index) -> list[pd.Timestamp]:
    out=[]; last=-10000
    for d in ds:
        if d not in idx: continue
        p=idx.get_loc(d)
        if isinstance(p,(int,np.integer)) and int(p)-last>COOLDOWN:
            out.append(d); last=int(p)
    return out


def ret(px: pd.DataFrame, d: pd.Timestamp, sym: str, h: int):
    if sym not in px.columns or d not in px.index: return None
    p=px.index.get_loc(d)
    if not isinstance(p,(int,np.integer)): return None
    a=int(p)+1; b=a+h
    if b>=len(px): return None
    x=px[sym].iloc[a]; y=px[sym].iloc[b]
    if pd.isna(x) or pd.isna(y) or float(x)<=0: return None
    return float(y/x-1-COST)


def stats(vals):
    a=np.asarray([v for v in vals if v is not None],dtype=float)
    return {"n":int(len(a)),"median":float(np.median(a)) if len(a) else None,"mean":float(np.mean(a)) if len(a) else None,"positive_rate":float(np.mean(a>0)) if len(a) else None}


def main():
    base=feature_frame(require_same_day=False)
    sig=build_canonical_signal_history(base)["signal"]
    px=load_subsector_prices(start="2016-09-01").sort_index()
    sf=build_subsector_frame(px)
    ds=independent([d for d in starts(sig) if d in sf.index],px.index)
    records=[]
    for d in ds:
        picks=rank_subsector_outperformance(sf.loc[d],top_n=3)
        if not picks: continue
        records.append((d,[p["symbol"] for p in picks]))
    result={"episodes":len(records),"method":"point-in-time ranking; next-session close execution; 10-session independent cooldown","horizons":{}}
    for h in HORIZONS:
        top1=[]; top3=[]; spy=[]; qqq=[]; smh=[]
        beat_spy=[]; beat_qqq=[]
        for d,picks in records:
            r1=ret(px,d,picks[0],h)
            rs=[ret(px,d,s,h) for s in picks]
            rs=[x for x in rs if x is not None]
            r3=float(np.mean(rs)) if rs else None
            s=ret(px,d,"SPY",h); q=ret(px,d,"QQQ",h); m=ret(px,d,"SMH",h)
            top1.append(r1); top3.append(r3); spy.append(s); qqq.append(q); smh.append(m)
            if r3 is not None and s is not None: beat_spy.append(r3>s)
            if r3 is not None and q is not None: beat_qqq.append(r3>q)
        result["horizons"][str(h)]={"top1":stats(top1),"top3_equal_weight":stats(top3),"SPY":stats(spy),"QQQ":stats(qqq),"SMH_static":stats(smh),"top3_beat_SPY_rate":float(np.mean(beat_spy)) if beat_spy else None,"top3_beat_QQQ_rate":float(np.mean(beat_qqq)) if beat_qqq else None}
    # latest point-in-time ranking
    last=sf.index.max(); result["latest"]={"date":str(last.date()),"ranking":rank_subsector_outperformance(sf.loc[last],top_n=5)}
    out=Path("artifacts/reentry_outperform_backtest"); out.mkdir(parents=True,exist_ok=True)
    (out/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

if __name__=="__main__": main()
