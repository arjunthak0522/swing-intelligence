import { getLatest } from '@/lib/reentry-data';

type EvidenceCell = {
  median_return: number;
  positive_rate: number;
  median_max_drawdown: number;
};

type Snapshot = {
  as_of: string;
  engine_version: string;
  signal: string;
  analog_decision: string;
  market_state: string;
  data_freshness: { same_day_complete?: boolean };
  current_inputs: {
    spy_drawdown_20d: number;
    pct_sp500_above_50dma: number;
    pct_sp500_above_200dma: number;
    breadth_1d_change: number;
    vix_5d_change: number;
    vix_vix3m_ratio: number;
  };
  extended_forward_evidence: {
    SPY: Record<string, EvidenceCell>;
    QQQ: Record<string, EvidenceCell>;
  };
};

const pct = (value: number, digits = 2) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)}%`;
const plainPct = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`;

export default async function Home() {
  const snapshot = (await getLatest()) as unknown as Snapshot;
  const horizons = [5, 7, 10, 15, 30, 60];
  const inputs = snapshot.current_inputs;

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="brand">RE-ENTRY</div>
          <div className="tagline">Know when waiting stops helping.</div>
        </div>
        <div className="freshness">
          <span className={snapshot.data_freshness.same_day_complete ? 'dot good' : 'dot bad'} />
          <div>
            <strong>{snapshot.data_freshness.same_day_complete ? 'ALL DATA CURRENT' : 'DATA INCOMPLETE'}</strong>
            <span>{snapshot.as_of} close · {snapshot.engine_version}</span>
          </div>
        </div>
      </header>

      <section className="heroGrid">
        <article className="heroCard primary">
          <span className="eyebrow">Historical backdrop</span>
          <h1>{snapshot.analog_decision}</h1>
          <p>Conditions similar to this market state remain historically constructive.</p>
        </article>
        <article className="heroCard">
          <span className="eyebrow">Fresh re-entry setup</span>
          <h2>{snapshot.signal}</h2>
          <p>{snapshot.market_state}</p>
        </article>
      </section>

      <section className="stateStrip">
        <Metric label="SPY pullback" value={pct(inputs.spy_drawdown_20d)} />
        <Metric label="Breadth >50DMA" value={plainPct(inputs.pct_sp500_above_50dma)} />
        <Metric label="Breadth >200DMA" value={plainPct(inputs.pct_sp500_above_200dma)} />
        <Metric label="Breadth today" value={`${(inputs.breadth_1d_change * 100).toFixed(1)} pp`} />
        <Metric label="VIX 5D" value={pct(inputs.vix_5d_change)} />
        <Metric label="VIX / VIX3M" value={inputs.vix_vix3m_ratio.toFixed(3)} />
      </section>

      <section className="panel">
        <div className="sectionHead">
          <div>
            <span className="eyebrow">40 closest prior environments</span>
            <h3>Historical Forward Outcomes</h3>
          </div>
          <span className="muted">Median return · win rate · typical max drawdown</span>
        </div>
        <div className="tableWrap">
          <table>
            <thead>
              <tr>
                <th>Horizon</th>
                <th>SPY return</th>
                <th>SPY win</th>
                <th>SPY typical DD</th>
                <th>QQQ return</th>
                <th>QQQ win</th>
                <th>QQQ typical DD</th>
              </tr>
            </thead>
            <tbody>
              {horizons.map((h) => {
                const spy = snapshot.extended_forward_evidence.SPY[String(h)];
                const qqq = snapshot.extended_forward_evidence.QQQ[String(h)];
                return (
                  <tr key={h}>
                    <td className="horizon">{h}D</td>
                    <td className={spy.median_return >= 0 ? 'positive' : 'negative'}>{pct(spy.median_return)}</td>
                    <td>{plainPct(spy.positive_rate)}</td>
                    <td className="risk">{pct(spy.median_max_drawdown)}</td>
                    <td className={qqq.median_return >= 0 ? 'positive' : 'negative'}>{pct(qqq.median_return)}</td>
                    <td>{plainPct(qqq.positive_rate)}</td>
                    <td className="risk">{pct(qqq.median_max_drawdown)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}
