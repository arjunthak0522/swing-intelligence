import Link from "next/link";
import { ArrowRight, Check, ShieldCheck } from "lucide-react";
import { getHistoricalEpisodeEvidence } from "../lib/historicalEvidence";
import { deriveCommercialState, getCanonicalCommercialSnapshot } from "../lib/commercial";

export const dynamic = "force-dynamic";

function pct(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? (value * 100).toFixed(1) + "%" : "Audit pending";
}

export default async function LandingPage() {
  const [snapshot, historical] = await Promise.all([
    getCanonicalCommercialSnapshot(),
    getHistoricalEpisodeEvidence(),
  ]);
  const state = deriveCommercialState(snapshot);
  const trialUrl = process.env.NEXT_PUBLIC_WHOP_TRIAL_URL || "/app";
  const validation = historical?.final_policy_validation?.SPY?.["30"];
  const sampleCount = historical?.retail_validation_summary?.final_independent_reentry_episodes;

  return (
    <main className="btfd-page">
      <nav className="btfd-nav">
        <Link href="/" className="btfd-wordmark">BTFD</Link>
        <div className="btfd-nav-actions">
          <Link href="/evidence" className="btfd-text-link">Evidence</Link>
          <Link href={trialUrl} className="btfd-button small">Try free</Link>
        </div>
      </nav>

      <section className="btfd-hero btfd-container">
        <div className="btfd-hero-copy">
          <span className="btfd-eyebrow">Market re-entry, simplified</span>
          <h1>Should you buy the dip yet?</h1>
          <p className="btfd-lede">
            BTFD watches the recovery after a market pullback and reduces the decision to one actionable choice:
            stay parked in SGOV, or move the sidelined allocation into VOO.
          </p>
          <div className="btfd-hero-actions">
            <Link href={trialUrl} className="btfd-button">Try BTFD free <ArrowRight size={17} /></Link>
            <Link href="/evidence" className="btfd-secondary-button">See the evidence</Link>
          </div>
          <p className="btfd-micro">Built for sidelined cash. Not a sell signal for an existing long-term portfolio.</p>
        </div>

        <div className="btfd-live-card">
          <div className="btfd-live-top">
            <span>Current BTFD state</span>
            <span className="btfd-live-dot">LIVE MODEL</span>
          </div>
          <div className={"btfd-state " + (state.label === "BUY VOO" ? "buy" : state.label === "WATCH" ? "watch" : "hold")}>
            {state.label}
          </div>
          <h2>{state.action}</h2>
          <p>{state.summary}</p>
          <div className="btfd-progress" aria-label="HOLD CASH to WATCH to BUY VOO progression">
            <span className={state.label === "HOLD CASH" ? "active" : ""}>HOLD CASH</span>
            <i />
            <span className={state.label === "WATCH" ? "active" : ""}>WATCH</span>
            <i />
            <span className={state.label === "BUY VOO" ? "active" : ""}>BUY VOO</span>
          </div>
        </div>
      </section>

      <section className="btfd-container btfd-section">
        <div className="btfd-section-heading">
          <span className="btfd-eyebrow">The entire product</span>
          <h2>Wait in SGOV until the evidence changes.</h2>
        </div>
        <div className="btfd-three">
          <article>
            <span className="btfd-step">01</span>
            <h3>Market pulls back</h3>
            <p>BTFD waits. The sidelined allocation stays in SGOV.</p>
          </article>
          <article>
            <span className="btfd-step">02</span>
            <h3>Recovery begins</h3>
            <p>WATCH means conditions are improving, but the allocation still stays in SGOV.</p>
          </article>
          <article>
            <span className="btfd-step">03</span>
            <h3>Buy threshold fires</h3>
            <p>BUY VOO means move the designated re-entry allocation from SGOV into VOO.</p>
          </article>
        </div>
      </section>

      <section className="btfd-proof-wrap">
        <div className="btfd-container btfd-proof">
          <div>
            <span className="btfd-eyebrow">Historical evidence</span>
            <h2>Every signal has to earn trust.</h2>
            <p>
              The commercial evidence layer will show all qualifying historical events, including weak outcomes and failed starts.
              Public performance claims remain locked until the commercial backtest audit is complete.
            </p>
            <Link href="/evidence" className="btfd-inline-link">Inspect the research dataset <ArrowRight size={16} /></Link>
          </div>
          <div className="btfd-proof-stats">
            <div><strong>{sampleCount ?? "Audit pending"}</strong><span>independent historical re-entry episodes in the current research archive</span></div>
            <div><strong>{pct(validation?.median_return)}</strong><span>30-trading-day median S&P 500 proxy return in the current research archive</span></div>
            <div><strong>{pct(validation?.positive_rate)}</strong><span>positive after 30 trading days in the current research archive</span></div>
          </div>
        </div>
      </section>

      <section className="btfd-container btfd-trust">
        <div>
          <ShieldCheck size={23} />
          <h3>One engine</h3>
          <p>The customer experience reads the canonical REENTRY_UNIFIED_v1 snapshot. It does not create a second signal.</p>
        </div>
        <div>
          <Check size={23} />
          <h3>No indicator homework</h3>
          <p>Market internals stay underneath the product. The primary decision stays SGOV or VOO.</p>
        </div>
        <div>
          <Check size={23} />
          <h3>No constant trading</h3>
          <p>BTFD is only about putting sidelined cash back to work after pullbacks.</p>
        </div>
      </section>

      <section className="btfd-final-cta">
        <div className="btfd-container">
          <span className="btfd-eyebrow">Stop guessing after the pullback</span>
          <h2>Know when waiting has stopped helping.</h2>
          <Link href={trialUrl} className="btfd-button light">Try BTFD free <ArrowRight size={17} /></Link>
        </div>
      </section>

      <footer className="btfd-footer btfd-container">
        <span>BTFD</span>
        <p>Generalized market intelligence only. Historical and hypothetical results do not guarantee future performance.</p>
      </footer>
    </main>
  );
}
