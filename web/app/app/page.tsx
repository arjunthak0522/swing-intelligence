import Link from "next/link";
import { ArrowRight, CheckCircle2, ChevronRight } from "lucide-react";
import { getHistoricalEpisodeEvidence } from "../../lib/historicalEvidence";
import { deriveCommercialState, formatEastern, getCanonicalCommercialSnapshot } from "../../lib/commercial";

export const dynamic = "force-dynamic";

function pct(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? (value * 100).toFixed(1) + "%" : "-";
}

export default async function MemberHome() {
  const [snapshot, historical] = await Promise.all([
    getCanonicalCommercialSnapshot(),
    getHistoricalEpisodeEvidence(),
  ]);
  const state = deriveCommercialState(snapshot);
  const metric = historical?.final_policy_validation?.SPY?.["30"];

  return (
    <main className="btfd-member">
      <header className="btfd-member-nav">
        <Link href="/" className="btfd-wordmark">BTFD</Link>
        <nav>
          <Link href="/app" className="active">Today</Link>
          <Link href="/evidence">Evidence</Link>
          <Link href="/research">Market internals</Link>
        </nav>
      </header>

      <section className="btfd-member-main">
        <div className="btfd-today-label">TODAY</div>
        <div className={"btfd-member-state " + (state.label === "BUY VOO" ? "buy" : state.label === "WATCH" ? "watch" : "hold")}>
          {state.label}
        </div>
        <h1>{state.action}</h1>
        <p className="btfd-member-summary">{state.summary}</p>
        <div className="btfd-member-meta">
          <span>{state.recovery}</span>
          <span>Updated {formatEastern(state.timestamp)}</span>
        </div>

        <div className="btfd-member-progress">
          <div className={state.label === "HOLD CASH" ? "active" : ""}><b>HOLD CASH</b><span>SGOV</span></div>
          <i />
          <div className={state.label === "WATCH" ? "active" : ""}><b>WATCH</b><span>SGOV</span></div>
          <i />
          <div className={state.label === "BUY VOO" ? "active" : ""}><b>BUY VOO</b><span>VOO</span></div>
        </div>

        <section className="btfd-member-grid">
          <article className="btfd-member-panel">
            <div className="btfd-panel-title"><span>Why</span><small>Plain English</small></div>
            <div className="btfd-why-list">
              {state.why.map((item) => (
                <div key={item}><CheckCircle2 size={18} /><span>{item}</span></div>
              ))}
            </div>
            <Link href="/research" className="btfd-panel-link">See market internals <ChevronRight size={16} /></Link>
          </article>

          <article className="btfd-member-panel">
            <div className="btfd-panel-title"><span>Historical context</span><small>Current research archive</small></div>
            <div className="btfd-context-number">{pct(metric?.median_return)}</div>
            <p>Median S&P 500 proxy return 30 trading days after historical re-entry signals.</p>
            <div className="btfd-context-row"><span>Positive after 30 days</span><b>{pct(metric?.positive_rate)}</b></div>
            <div className="btfd-context-row"><span>Observations</span><b>{metric?.n ?? "-"}</b></div>
            <Link href="/evidence" className="btfd-panel-link">View the full evidence <ChevronRight size={16} /></Link>
          </article>
        </section>

        <section className="btfd-action-note">
          <div>
            <span>What BTFD means by cash</span>
            <h2>SGOV is the waiting vehicle.</h2>
            <p>HOLD CASH and WATCH both mean keep the designated re-entry allocation in SGOV. BUY VOO means move that allocation into VOO.</p>
          </div>
          <Link href="/evidence" className="btfd-secondary-button">How the model is tested <ArrowRight size={16} /></Link>
        </section>

        <p className="btfd-disclosure">
          BTFD is generalized market intelligence. It does not know your financial circumstances and does not tell you to sell an existing long-term VOO position.
        </p>
      </section>
    </main>
  );
}
