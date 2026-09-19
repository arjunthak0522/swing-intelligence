import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { getHistoricalEpisodeEvidence } from "../../lib/historicalEvidence";

function pct(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) ? (value * 100).toFixed(2) + "%" : "-";
}

export default async function EvidencePage() {
  const historical = await getHistoricalEpisodeEvidence();
  const spy = historical?.final_policy_validation?.SPY;
  const horizons = ["5", "10", "15", "30", "60"];

  return (
    <main className="btfd-evidence-page">
      <header className="btfd-member-nav">
        <Link href="/" className="btfd-wordmark">BTFD</Link>
        <Link href="/app" className="btfd-back"><ArrowLeft size={16} /> Today</Link>
      </header>
      <section className="btfd-evidence-main">
        <span className="btfd-eyebrow">Evidence</span>
        <h1>Show the wins. Show the misses.</h1>
        <p className="btfd-evidence-lede">
          This is the current internal validation archive for the S&P 500 timing policy. It is shown for product development.
          Public marketing claims remain disabled until the commercial audit verifies reconstruction, timestamps, clustering, look-ahead controls and execution assumptions.
        </p>

        <div className="btfd-audit-banner">
          <b>Commercial audit required before launch</b>
          <span>Current archive: {historical?.provenance?.sample_start || "-"} through {historical?.provenance?.sample_end || "-"}</span>
        </div>

        <div className="btfd-evidence-table-wrap">
          <table className="btfd-evidence-table">
            <thead>
              <tr>
                <th>After signal</th>
                <th>Observations</th>
                <th>Median return</th>
                <th>Average return</th>
                <th>Positive</th>
                <th>Median adverse move</th>
              </tr>
            </thead>
            <tbody>
              {horizons.map((h) => {
                const row = spy?.[h];
                return (
                  <tr key={h}>
                    <td>{h} trading days</td>
                    <td>{row?.n ?? "-"}</td>
                    <td>{pct(row?.median_return)}</td>
                    <td>{pct(row?.mean_return)}</td>
                    <td>{pct(row?.positive_rate)}</td>
                    <td>{pct(row?.median_mae)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <section className="btfd-methodology-grid">
          <div><span>01</span><h3>No cherry-picking</h3><p>The public product must expose every independent qualifying event, including weak and negative outcomes.</p></div>
          <div><span>02</span><h3>No look-ahead</h3><p>Each signal must use only information that was available at the timestamp assigned to that signal.</p></div>
          <div><span>03</span><h3>One benchmark story</h3><p>The customer action is VOO. Longer history can use a clearly disclosed S&P 500 proxy where VOO history is unavailable.</p></div>
          <div><span>04</span><h3>Delay must be tested</h3><p>The commercial proof needs to compare the actual signal with waiting additional trading days, not just report forward returns.</p></div>
        </section>
      </section>
    </main>
  );
}
