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
  analog_interpretation?: string;
  market_state: string;
  caveats?: string[];
  data_freshness: { same_day_complete?: boolean };
  current_inputs: {
    spy_drawdown_20d: number;
    spy_return_5d: number;
    pct_sp500_above_50dma: number;
    pct_sp500_above_200dma: number;
    breadth_1d_change: number;
    breadth_3d_change: number;
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
const pp = (value: number, digits = 1) => `${value >= 0 ? '+' : ''}${(value * 100).toFixed(digits)} pp`;

function freshSetupLabel(signal: string) {
  if (signal === 'RE-ENTER') return 'YES';
  if (signal === 'WAIT') return 'NOT YET';
  return 'NO';
}

function freshSetupHeadline(signal: string) {
  if (signal === 'RE-ENTER') return 'A fresh re-entry setup is active.';
  if (signal === 'WAIT') return 'Weakness is present, but the setup is not ready.';
  return 'There is no fresh dip-entry setup today.';
}

function plainMeaning(snapshot: Snapshot) {
  if (snapshot.signal === 'RE-ENTER') {
    return 'Weakness is present and the historical analog evidence supports re-entry now rather than continuing to wait.';
  }
  if (snapshot.signal === 'WAIT') {
    return 'The market is weak enough to watch, but the historical analog evidence has not confirmed a re-entry yet.';
  }
  if (snapshot.analog_decision === 'YES' || snapshot.analog_decision === 'STRONG YES') {
    return 'Recent weakness has already repaired enough that this is no longer a new dip trigger. The broader historical backdrop is still constructive.';
  }
  return 'The engine does not see a fresh re-entry setup today.';
}

export default async function Home() {
  const snapshot = (await getLatest()) as unknown as Snapshot;
  const inputs = snapshot.current_inputs;
  const dataCurrent = Boolean(snapshot.data_freshness.same_day_complete);
  const setupLabel = freshSetupLabel(snapshot.signal);
  const evidenceHorizons = [7, 30, 60];

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="brand">RE-ENTRY</div>
          <div className="tagline">Know when waiting stops helping.</div>
        </div>
        <div className="freshness">
          <span className={dataCurrent ? 'dot good' : 'dot bad'} />
          <div>
            <strong>{dataCurrent ? 'DATA CURRENT' : 'DATA INCOMPLETE'}</strong>
            <span>{snapshot.as_of} close · {snapshot.engine_version}</span>
          </div>
        </div>
      </header>

      <section className="decisionHero">
        <div className="question">Is there a fresh dip to buy?</div>
        <div className={`answer ${setupLabel === 'YES' ? 'yes' : setupLabel === 'NOT YET' ? 'wait' : 'no'}`}>{setupLabel}</div>
        <h1>{freshSetupHeadline(snapshot.signal)}</h1>
        <p className="heroCopy">{plainMeaning(snapshot)}</p>
        <div className="heroFacts">
          <div>
            <span>Fresh setup</span>
            <strong>{snapshot.signal}</strong>
          </div>
          <div>
            <span>Forward backdrop</span>
            <strong>{snapshot.analog_decision === 'YES' || snapshot.analog_decision === 'STRONG YES' ? 'CONSTRUCTIVE' : snapshot.analog_decision}</strong>
          </div>
          <div>
            <span>Market state</span>
            <strong>{snapshot.market_state.toUpperCase()}</strong>
          </div>
        </div>
      </section>

      <section className="meaningPanel">
        <div className="sectionKicker">What this means</div>
        <div className="meaningGrid">
          <div className="meaningItem">
            <span className="number">01</span>
            <div>
              <h2>For someone already invested</h2>
              <p>This is not a sell or risk-off signal. RE-ENTRY only evaluates whether current weakness is attractive for putting cash back to work.</p>
            </div>
          </div>
          <div className="meaningItem">
            <span className="number">02</span>
            <div>
              <h2>For someone still in cash</h2>
              <p>{snapshot.signal === 'RE-ENTER' ? 'The engine is actively signaling a re-entry setup.' : snapshot.signal === 'WAIT' ? 'Keep watching. Weakness exists, but the engine has not confirmed re-entry.' : 'The engine is not issuing a new dip-entry signal today. The market has already repaired part of the prior weakness.'}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="diagnosis">
        <div className="sectionHeadSimple">
          <div>
            <div className="sectionKicker">What the engine sees</div>
            <h2>Three questions, in order.</h2>
          </div>
        </div>
        <div className="diagnosisGrid">
          <article className="diagnosisCard">
            <span className="step">1 · DAMAGE</span>
            <strong className="diagnosisState">{inputs.spy_drawdown_20d <= -0.01 ? 'PRESENT' : 'LIGHT'}</strong>
            <p>SPY is {plainPct(Math.abs(inputs.spy_drawdown_20d), 2)} below its 20-day high.</p>
            <small>Price damage asks whether enough weakness has occurred to matter.</small>
          </article>
          <article className="diagnosisCard">
            <span className="step">2 · SELLING PRESSURE</span>
            <strong className="diagnosisState">{snapshot.market_state.toLowerCase().includes('stabil') ? 'STABILIZING' : snapshot.market_state.toUpperCase()}</strong>
            <p>Breadth changed {pp(inputs.breadth_1d_change)} today while VIX changed {pct(inputs.vix_5d_change)} over 5 days.</p>
            <small>This asks whether stress is still accelerating or beginning to repair.</small>
          </article>
          <article className="diagnosisCard">
            <span className="step">3 · HISTORICAL ANALOGS</span>
            <strong className="diagnosisState">{snapshot.analog_decision === 'YES' || snapshot.analog_decision === 'STRONG YES' ? 'CONSTRUCTIVE' : snapshot.analog_decision}</strong>
            <p>40 prior market environments are compared with today.</p>
            <small>This asks what happened after the most similar combinations of damage, breadth and volatility.</small>
          </article>
        </div>
      </section>

      <section className="outcomesPanel">
        <div className="sectionHeadSimple outcomesHead">
          <div>
            <div className="sectionKicker">Historical evidence</div>
            <h2>What happened after similar conditions?</h2>
            <p>Median forward return, share of positive outcomes, and the typical maximum path drawdown across the 40 closest prior environments.</p>
          </div>
        </div>
        <div className="assetBlocks">
          {(['SPY', 'QQQ'] as const).map((symbol) => (
            <article className="assetBlock" key={symbol}>
              <div className="assetTitle">
                <strong>{symbol}</strong>
                <span>{symbol === 'SPY' ? 'S&P 500' : 'Nasdaq 100'}</span>
              </div>
              <div className="horizonGrid">
                {evidenceHorizons.map((h) => {
                  const cell = snapshot.extended_forward_evidence[symbol][String(h)];
                  return (
                    <div className="horizonCard" key={h}>
                      <span className="hLabel">{h === 7 ? '1 WEEK' : h === 30 ? '1 MONTH' : '2 MONTHS'}</span>
                      <strong className={cell.median_return >= 0 ? 'positive' : 'negative'}>{pct(cell.median_return)}</strong>
                      <div className="microRow"><span>Positive</span><b>{plainPct(cell.positive_rate)}</b></div>
                      <div className="microRow"><span>Typical drawdown</span><b className="risk">{pct(cell.median_max_drawdown)}</b></div>
                    </div>
                  );
                })}
              </div>
            </article>
          ))}
        </div>
        <p className="footnote">Typical drawdown is based on daily closes, not intraday lows. Historical analogs are evidence, not a guaranteed forecast.</p>
      </section>

      <section className="signalsPanel">
        <div className="sectionHeadSimple">
          <div>
            <div className="sectionKicker">Signals & indicators</div>
            <h2>Exactly what the engine uses.</h2>
            <p>The interface translates these into the three questions above. The raw inputs remain visible for transparency.</p>
          </div>
        </div>
        <div className="signalFamilies">
          <SignalFamily
            title="Price damage"
            question="Has the market weakened enough to matter?"
            items={[
              ['SPY drawdown from 20-day high', pct(inputs.spy_drawdown_20d)],
              ['SPY 5-day return', pct(inputs.spy_return_5d)],
            ]}
          />
          <SignalFamily
            title="Market breadth"
            question="How much of the market is weak, and is participation repairing?"
            items={[
              ['S&P 500 above 50DMA', plainPct(inputs.pct_sp500_above_50dma)],
              ['S&P 500 above 200DMA', plainPct(inputs.pct_sp500_above_200dma)],
              ['Breadth 1-day change', pp(inputs.breadth_1d_change)],
              ['Breadth 3-day change', pp(inputs.breadth_3d_change)],
            ]}
          />
          <SignalFamily
            title="Volatility"
            question="Is fear still building, or is stress normalizing?"
            items={[
              ['VIX 5-day change', pct(inputs.vix_5d_change)],
              ['VIX / VIX3M', inputs.vix_vix3m_ratio.toFixed(3)],
            ]}
          />
          <SignalFamily
            title="Historical analogs"
            question="What happened after environments most similar to today?"
            items={[
              ['Closest prior environments', '40'],
              ['Decision', snapshot.analog_decision],
              ['Forward windows', '5 / 7 / 10 / 15 / 30 / 60D'],
            ]}
          />
        </div>
      </section>

      <section className="methodologyBar">
        <div>
          <strong>Important</strong>
          <span>RE-ENTRY is a correction re-entry decision tool, not a general market-timing or sell system.</span>
        </div>
        <div className="methodologyMeta">40 analogs · completed daily closes · 10 bps modeled round-trip cost</div>
      </section>
    </main>
  );
}

function SignalFamily({ title, question, items }: { title: string; question: string; items: [string, string][] }) {
  return (
    <article className="signalFamily">
      <h3>{title}</h3>
      <p>{question}</p>
      <div className="signalRows">
        {items.map(([label, value]) => (
          <div className="signalRow" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </article>
  );
}
