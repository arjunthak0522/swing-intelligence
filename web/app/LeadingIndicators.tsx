type LeadingIndicator = {
  name?: string;
  state?: string;
  direction?: string;
  role?: string;
  decision_input?: boolean;
  benchmark?: string;
  why_it_matters?: string;
  freshness_type?: string;
  last_updated?: string | null;
  source?: string;
  validation_status?: string;
  breadth_ratio_10ema?: number;
  classic_thrust_triggered?: boolean;
  classic_setup_active?: boolean;
  nymo?: number;
  namo?: number;
  nymo_change?: number;
  namo_change?: number;
  pct_above_5dma?: number;
  pct_above_10dma?: number;
  change_5dma_points?: number;
  change_10dma_points?: number;
  coverage_pct?: number;
  hyg_lqd_ratio?: number;
  change_1d?: number;
  change_5d?: number;
};

type LeadingBlock = {
  version?: string;
  decision_input?: boolean;
  changes_deploy_trigger?: boolean;
  changes_recovery_stage?: boolean;
  purpose?: string;
  indicators?: Record<string, LeadingIndicator>;
  interpretation?: string;
};

const num=(v?:number,d=2)=>typeof v==="number"&&Number.isFinite(v)?v.toFixed(d):"UNAVAILABLE";
const pct=(v?:number,d=1)=>typeof v==="number"&&Number.isFinite(v)?`${v.toFixed(d)}%`:"UNAVAILABLE";
const ret=(v?:number)=>typeof v==="number"&&Number.isFinite(v)?`${v>=0?"+":""}${(v*100).toFixed(2)}%`:"UNAVAILABLE";
const signed=(v?:number,d=1)=>typeof v==="number"&&Number.isFinite(v)?`${v>=0?"+":""}${v.toFixed(d)}`:"UNAVAILABLE";

function tone(indicator:LeadingIndicator){
  const s=(indicator.state||"").toUpperCase();
  const d=(indicator.direction||"").toUpperCase();
  if(s.includes("THRUST_TRIGGERED")||s.includes("TURNING_UP")||s.includes("IMPROVING")||s.includes("BROADENING")||s.includes("ACCELERATING_UP"))return"leading-good";
  if(s.includes("DETERIORATING")||s.includes("WEAKENING")||s.includes("ACCELERATING_DOWN"))return"leading-bad";
  if(d==="RISING")return"leading-good";
  if(d==="FALLING")return"leading-bad";
  return"leading-neutral";
}

function readout(key:string,i:LeadingIndicator){
  if(key==="zweig_breadth_thrust")return `10-day breadth ratio ${num(i.breadth_ratio_10ema,3)}${i.classic_thrust_triggered?" · CLASSIC THRUST FIRED":i.classic_setup_active?" · setup active":""}`;
  if(key==="mcclellan_velocity")return `NYMO ${num(i.nymo)} (${signed(i.nymo_change)}) · NAMO ${num(i.namo)} (${signed(i.namo_change)})`;
  if(key==="nasdaq_short_breadth")return `Above 5D ${pct(i.pct_above_5dma)} (${signed(i.change_5dma_points)} pts) · Above 10D ${pct(i.pct_above_10dma)} (${signed(i.change_10dma_points)} pts)`;
  if(key==="credit_risk_turn")return `HYG/LQD ${num(i.hyg_lqd_ratio,4)} · 1D ${ret(i.change_1d)} · 5D ${ret(i.change_5d)}`;
  return"Current readout unavailable";
}

export default function LeadingIndicators({washout}:{washout:any}){
  const block:LeadingBlock|undefined=washout?.leading_indicators;
  const entries=Object.entries(block?.indicators||{});
  if(!entries.length)return null;
  return <section className="card section-card leading-indicators">
    <style>{`
      .leading-indicators{background:linear-gradient(145deg,#fbfaf7 0%,#f7faf8 58%,#f4f6f2 100%)}
      .leading-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:15px}
      .leading-head h2{margin:4px 0 5px;font-size:25px;letter-spacing:-.035em}.leading-head p{margin:0;max-width:680px;font-size:10px;line-height:1.55;color:var(--muted)}
      .leading-pill{font-size:8px;font-weight:900;letter-spacing:.07em;border:1px solid var(--line);border-radius:999px;padding:7px 9px;white-space:nowrap;background:rgba(255,255,255,.6)}
      .leading-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
      .leading-card{position:relative;border:1px solid var(--line);border-radius:15px;padding:13px;background:rgba(255,255,255,.6);overflow:hidden}.leading-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#a8aaa4}.leading-card.leading-good:before{background:var(--green)}.leading-card.leading-bad:before{background:var(--red)}
      .leading-title{font-size:10px;font-weight:900}.leading-meta{display:flex;gap:6px;flex-wrap:wrap;margin:7px 0 9px}.leading-state,.leading-direction{display:inline-block;padding:4px 7px;border-radius:999px;border:1px solid currentColor;font-size:8px;font-weight:900;letter-spacing:.045em}.leading-good .leading-state{color:var(--green)}.leading-bad .leading-state{color:var(--red)}.leading-direction{color:var(--muted)}
      .leading-readout{font-size:12px;font-weight:800;line-height:1.42}.leading-why{margin:9px 0 0;font-size:10px;line-height:1.5;color:#3f443d}.leading-why b{display:block;font-size:8px;letter-spacing:.08em;color:var(--muted);margin-bottom:2px}.leading-benchmark{margin-top:8px;padding:7px 8px;border-radius:9px;background:rgba(240,238,232,.58);font-size:9px;line-height:1.45;color:var(--muted)}.leading-foot{margin:10px 0 0;font-size:9px;line-height:1.45;color:var(--muted)}
      @media(max-width:760px){.leading-grid{grid-template-columns:1fr}.leading-head{display:block}.leading-pill{display:inline-block;margin-top:10px}}
    `}</style>
    <div className="leading-head"><div><span className="kicker">LEADING INDICATORS</span><h2>Are internals turning before the recovery looks obvious?</h2><p>{block?.purpose||"Early-turn context for breadth and credit."}</p></div><div className="leading-pill">CONTEXT ONLY · DOES NOT VOTE</div></div>
    <div className="leading-grid">{entries.map(([key,i])=><div key={key} className={`leading-card ${tone(i)}`}>
      <div className="leading-title">{i.name||key.replaceAll("_"," ").toUpperCase()}</div>
      <div className="leading-meta"><span className="leading-state">{(i.state||"UNAVAILABLE").replaceAll("_"," ")}</span><span className="leading-direction">{(i.direction||"UNAVAILABLE").replaceAll("_"," ")}</span></div>
      <div className="leading-readout">{readout(key,i)}</div>
      <p className="leading-why"><b>WHY IT MATTERS FOR RE-ENTRY</b>{i.why_it_matters||"Research-only leading context."}</p>
      {i.benchmark?<div className="leading-benchmark">{i.benchmark}</div>:null}
    </div>)}</div>
    <p className="leading-foot">{block?.interpretation||"These indicators are context only and cannot change the RE-ENTRY decision."}</p>
  </section>;
}
