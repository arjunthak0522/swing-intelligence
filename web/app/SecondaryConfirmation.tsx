type Family = {
  name?: string;
  state?: string;
  supportive?: boolean;
  benchmark?: string;
  source?: string;
  validation_status?: string;
  validation_note?: string;
  retail_explanation?: string;
  signal_behavior?: "CONTRARIAN" | "CONFIRMING" | "CONTEXTUAL" | string;
  behavior_explanation?: string;
  freshness_type?: "INTRADAY_SNAPSHOT" | "DAILY_CLOSE" | "UNAVAILABLE" | string;
  last_updated?: string | null;
  current_ratio?: number;
  prior_ratio?: number;
  nasdaq_advance_share?: number;
  supportive_components?: number;
  equity_put_call?: number;
  index_put_call?: number;
  total_put_call?: number;
};

type Overlay = {
  version?: string;
  decision_input?: boolean;
  changes_deploy_trigger?: boolean;
  changes_recovery_stage?: boolean;
  supportive_family_count?: number;
  family_count?: number;
  interpretation?: string;
  families?: Record<string, Family>;
};

const pct = (v?: number) => typeof v === "number" && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : "UNAVAILABLE";
const num = (v?: number, d = 2) => typeof v === "number" && Number.isFinite(v) ? v.toFixed(d) : "UNAVAILABLE";
const behaviorLabel = (v?: string) => (v || "CONTEXTUAL").replaceAll("_", " ");
const freshnessLabel = (family: Family) => {
  const kind = (family.freshness_type || "UNAVAILABLE").replaceAll("_", " ");
  return family.last_updated ? `${kind} · updated ${family.last_updated}` : kind;
};

function readout(key: string, family: Family) {
  if (key === "vol_structure") return `VIX/VIX3M ${num(family.current_ratio)} · prior ${num(family.prior_ratio)}`;
  if (key === "breadth_thrust") return `Nasdaq advancing share ${pct(family.nasdaq_advance_share)}`;
  if (key === "risk_appetite") return `${family.supportive_components ?? 0}/3 risk-on relationships confirming`;
  if (key === "options_sentiment") return `Equity P/C ${num(family.equity_put_call)} · Index P/C ${num(family.index_put_call)}`;
  return "Current readout unavailable";
}

function tone(state?: string, supportive?: boolean) {
  const s = (state || "").toUpperCase();
  if (s.includes("ACUTE") || s.includes("DEFENSIVE")) return "secondary-bad";
  if (supportive || s.includes("NORMALIZED") || s.includes("BROAD") || s.includes("THRUST")) return "secondary-good";
  if (s.includes("BUILDING") || s.includes("FEAR") || s.includes("BACKWARDATION") || s.includes("MIXED")) return "secondary-warn";
  return "secondary-neutral";
}

export default function SecondaryConfirmation({ washout }: { washout: any }) {
  const overlay: Overlay | undefined = washout?.unified_engine?.secondary_confirmation || washout?.secondary_confirmation;
  if (!overlay?.families) return null;
  const entries = Object.entries(overlay.families);
  return <section className="card section-card secondary-confirmation">
    <style>{`
      .secondary-confirmation{background:linear-gradient(145deg,#fbfaf7 0%,#f7faf8 52%,#f3f7f4 100%)}
      .secondary-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin-bottom:16px}.secondary-score{font-size:11px;font-weight:900;border:1px solid rgba(47,118,80,.22);background:rgba(47,118,80,.07);padding:8px 10px;border-radius:999px;white-space:nowrap}
      .secondary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.secondary-card{position:relative;border:1px solid var(--line);border-radius:15px;padding:14px;background:rgba(255,255,255,.58);overflow:hidden}.secondary-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:#a8aaa4}.secondary-card.secondary-good:before{background:var(--green)}.secondary-card.secondary-warn:before{background:var(--amber)}.secondary-card.secondary-bad:before{background:var(--red)}
      .secondary-title{font-size:10px;font-weight:850}.secondary-meta{display:flex;flex-wrap:wrap;gap:5px;margin:8px 0 9px}.secondary-state,.secondary-behavior{display:inline-block;padding:4px 7px;border-radius:999px;border:1px solid currentColor;font-size:8px;font-weight:900;letter-spacing:.045em}.secondary-behavior{color:#5d625b}.secondary-good .secondary-state{color:var(--green)}.secondary-warn .secondary-state{color:var(--amber)}.secondary-bad .secondary-state{color:var(--red)}
      .secondary-readout{font-size:12px;font-weight:800;line-height:1.35}.secondary-plain,.secondary-behavior-copy{margin:9px 0 0;font-size:10px;line-height:1.5;color:#3f443d}.secondary-plain b,.secondary-behavior-copy b{display:block;font-size:8px;letter-spacing:.08em;color:var(--muted);margin-bottom:2px}.secondary-freshness{margin-top:8px;font-size:8px;font-weight:850;letter-spacing:.04em;color:#565b54}.secondary-benchmark{margin-top:9px;padding:8px;border-radius:9px;background:#f0eee8;font-size:9px;line-height:1.45;color:#53574f}.secondary-validation{margin-top:8px;font-size:8px;font-weight:850;letter-spacing:.04em;color:var(--muted)}.secondary-note{margin:6px 0 0;font-size:9px;line-height:1.42;color:var(--muted)}
      .secondary-foot{margin:13px 0 0;font-size:10px;line-height:1.5;color:var(--muted)}
      @media(max-width:900px){.secondary-grid{grid-template-columns:1fr 1fr}}@media(max-width:620px){.secondary-grid{grid-template-columns:1fr}.secondary-head{display:block}.secondary-score{display:inline-block;margin-top:10px}}
    `}</style>
    <div className="secondary-head"><div><span className="kicker">SECONDARY CONFIRMATION</span><h2 style={{margin:"4px 0 0",fontSize:25,letterSpacing:"-.035em"}}>Is the recovery broadening?</h2></div><div className="secondary-score">{overlay.supportive_family_count ?? 0}/{overlay.family_count ?? entries.length} supportive</div></div>
    <div className="secondary-grid">{entries.map(([key,family]) => <div key={key} className={`secondary-card ${tone(family.state,family.supportive)}`}>
      <div className="secondary-title">{family.name || key.replaceAll("_"," ").toUpperCase()}</div>
      <div className="secondary-meta"><span className="secondary-state">{(family.state || "UNAVAILABLE").replaceAll("_"," ")}</span><span className="secondary-behavior">{behaviorLabel(family.signal_behavior)}</span></div>
      <div className="secondary-readout">{readout(key,family)}</div>
      <div className="secondary-freshness">{freshnessLabel(family)}</div>
      <p className="secondary-plain"><b>WHAT THIS MEANS</b>{family.retail_explanation || "Plain-English interpretation unavailable."}</p>
      <p className="secondary-behavior-copy"><b>HOW TO READ IT</b>{family.behavior_explanation || "Signal behavior explanation unavailable."}</p>
      <div className="secondary-benchmark">{family.benchmark || "Benchmark unavailable"}</div>
      <div className="secondary-validation">{(family.validation_status || "RESEARCH PENDING").replaceAll("_"," ")}</div>
      <p className="secondary-note">{family.validation_note}</p>
    </div>)}</div>
    <p className="secondary-foot">{overlay.interpretation} Contrarian readings are setups, not automatic buy signals; confirmation comes from the reversal/repair that follows. These signals remain descriptive until their incremental historical value is proven.</p>
  </section>;
}
