"use client";

import { useEffect, useState } from "react";
import { ChevronDown, CircleAlert, CircleCheck, Clock3 } from "lucide-react";

type ValidationRow = {
  market_date: string;
  snapshot_label: string;
  intraday_state: "STABLE" | "WATCH" | "CAUTION" | "DETERIORATING" | string;
  deterioration_score: number;
  spy_change_pct: number | null;
  qqq_change_pct: number | null;
  vix_change_pct: number | null;
  sectors_positive_share: number | null;
  subsectors_positive_share: number | null;
  official_signal_before_close: string | null;
  official_signal_at_close: string | null;
  state_changed: boolean | null;
  classification: "PENDING" | "CORRECT WARNING" | "FALSE WARNING" | "MISSED CHANGE" | "CORRECT STABLE" | string;
};

type TimeStats = {
  completed: number;
  warnings: number;
  correct_warnings: number;
  warning_hit_rate: number | null;
  stable_observations: number;
  stable_change_rate: number | null;
};

type Report = {
  generated_at: string;
  latest_market_date: string | null;
  latest: ValidationRow[];
  by_snapshot_time: Record<string, TimeStats>;
  total_completed_snapshot_observations: number;
  methodology: string;
};

const REPORT_URL = "https://gexrdfzxmlnaawzmtlrk.supabase.co/functions/v1/reentry-intraday-shadow-report";

const pct = (value: number | null | undefined, digits = 0) =>
  typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "-";

function stateClass(value: string) {
  if (value === "STABLE") return "good-text";
  if (value === "WATCH" || value === "CAUTION") return "warn-text";
  if (value === "DETERIORATING") return "bad-text";
  return "muted";
}

function resultClass(value: string) {
  if (value === "CORRECT WARNING" || value === "CORRECT STABLE") return "good-text";
  if (value === "FALSE WARNING" || value === "MISSED CHANGE") return "bad-text";
  return "muted";
}

export default function ShadowValidationPanel() {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    fetch(REPORT_URL, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data) => { if (active) setReport(data as Report); })
      .catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, []);

  return (
    <details className="card section-card shadow-validation">
      <summary className="shadow-summary">
        <div className="section-heading">
          <div>
            <span className="kicker">INTRADAY SHADOW VALIDATION</span>
            <h2>Is the warning layer actually working?</h2>
            <p className="section-intro">Forward evidence only. The intraday layer is being scored against the official completed-close RE-ENTRY state without changing that state.</p>
          </div>
          <div className="shadow-summary-status"><span className="pill">RESEARCH ONLY</span><ChevronDown size={18} /></div>
        </div>
      </summary>

      <div className="shadow-body">
        {error ? <div className="notice"><CircleAlert size={16} /> Shadow-validation evidence is temporarily unavailable.</div> : !report ? <div className="notice"><Clock3 size={16} /> Loading forward-validation evidence...</div> : <>
          <div className="shadow-latest-head">
            <div><span className="summary-label">LATEST MARKET DAY</span><b>{report.latest_market_date ?? "No observations yet"}</b></div>
            <div><span className="summary-label">COMPLETED SCORED OBSERVATIONS</span><b>{report.total_completed_snapshot_observations}</b></div>
          </div>

          {report.latest.length > 0 ? <div className="shadow-table-wrap"><div className="shadow-table">
            <div className="shadow-row shadow-head"><span>Time</span><span>Intraday read</span><span>SPY</span><span>QQQ</span><span>VIX</span><span>Close result</span></div>
            {report.latest.map((row) => <div className="shadow-row" key={`${row.market_date}-${row.snapshot_label}`}>
              <b>{row.snapshot_label} ET</b>
              <span><strong className={stateClass(row.intraday_state)}>{row.intraday_state}</strong><small>{row.deterioration_score}/3 risks</small></span>
              <span>{pct(row.spy_change_pct, 2)}</span>
              <span>{pct(row.qqq_change_pct, 2)}</span>
              <span>{pct(row.vix_change_pct, 2)}</span>
              <span><strong className={resultClass(row.classification)}>{row.classification === "PENDING" ? "Pending close" : row.classification}</strong>{row.official_signal_at_close ? <small>{row.official_signal_before_close} → {row.official_signal_at_close}</small> : <small>Official close not scored yet</small>}</span>
            </div>)}
          </div></div> : <div className="notice">No shadow observations have been stored yet.</div>}

          <div className="shadow-time-grid">
            {["10:30","11:30","13:30","14:30"].map((label) => {
              const s = report.by_snapshot_time?.[label];
              return <div key={label}><small>{label} ET</small><b>{s?.warning_hit_rate == null ? "Not enough data" : `${(s.warning_hit_rate * 100).toFixed(0)}% warning hit rate`}</b><span>{s?.completed ?? 0} completed observations</span></div>;
            })}
          </div>

          <div className="shadow-note"><CircleCheck size={15} /><span><b>Thresholds remain frozen during shadow validation.</b> CAUTION/DETERIORATING counts as a warning. STABLE/WATCH counts as no warning. We do not retune the model to individual days.</span></div>
        </>}
      </div>

      <style jsx>{`
        .shadow-validation{padding:0;overflow:hidden}.shadow-summary{list-style:none;cursor:pointer;padding:22px 24px}.shadow-summary::-webkit-details-marker{display:none}.shadow-summary .section-heading{margin:0}.shadow-summary-status{display:flex;align-items:center;gap:10px}.shadow-summary-status svg{transition:transform .16s}.shadow-validation[open] .shadow-summary-status svg{transform:rotate(180deg)}.shadow-body{border-top:1px solid var(--line);padding:18px 24px 24px}.shadow-latest-head{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}.shadow-latest-head>div{padding:12px 14px;border:1px solid var(--line);border-radius:12px}.shadow-latest-head span,.shadow-latest-head b{display:block}.shadow-latest-head b{margin-top:4px}.shadow-table-wrap{overflow-x:auto}.shadow-table{min-width:760px;border:1px solid var(--line);border-radius:12px;overflow:hidden}.shadow-row{display:grid;grid-template-columns:90px 1.25fr .7fr .7fr .7fr 1.4fr;gap:12px;align-items:center;padding:12px 14px;border-top:1px solid var(--line);font-size:11px}.shadow-row:first-child{border-top:0}.shadow-head{background:#f2efe8;color:var(--muted);font-size:9px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}.shadow-row span{min-width:0}.shadow-row strong,.shadow-row small{display:block}.shadow-row small{margin-top:2px;color:var(--muted);font-size:9px}.warn-text{color:var(--amber)}.shadow-time-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:14px}.shadow-time-grid>div{padding:12px;border:1px solid var(--line);border-radius:12px}.shadow-time-grid small,.shadow-time-grid b,.shadow-time-grid span{display:block}.shadow-time-grid small,.shadow-time-grid span{color:var(--muted);font-size:9px}.shadow-time-grid b{margin:4px 0;font-size:12px}.shadow-note{display:flex;gap:8px;align-items:flex-start;margin-top:12px;padding:11px 13px;background:#f2efe8;border-radius:11px;color:var(--muted);font-size:10px;line-height:1.5}@media(max-width:760px){.shadow-latest-head,.shadow-time-grid{grid-template-columns:1fr 1fr}.shadow-summary{padding:18px}.shadow-body{padding:16px 18px 20px}}
      `}</style>
    </details>
  );
}
