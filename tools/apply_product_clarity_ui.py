from pathlib import Path

page_path = Path('web/app/page.tsx')
css_path = Path('web/app/globals.css')
page = page_path.read_text()
css = css_path.read_text()

# Imports.
old = 'import MarketMovementTables from "./MarketMovementTables";\n'
new = old + 'import HistoricalEvidence from "./HistoricalEvidence";\nimport { getHistoricalEpisodeEvidence } from "../lib/historicalEvidence";\n'
if new not in page:
    if old not in page:
        raise SystemExit('MarketMovementTables import anchor missing')
    page = page.replace(old, new, 1)

# Friendly date helper.
anchor = '''function StatusPill({ children }: { children: React.ReactNode }) {\n  return <span className="pill">{children}</span>;\n}\n'''
helper = '''function StatusPill({ children }: { children: React.ReactNode }) {\n  return <span className="pill">{children}</span>;\n}\n\nfunction formatDate(value?: string | null) {\n  if (!value) return "—";\n  const date = new Date(`${value}T00:00:00Z`);\n  if (Number.isNaN(date.getTime())) return value;\n  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });\n}\n\nfunction ProductPurpose() {\n  return (\n    <section className="card purpose-card">\n      <span className="kicker">WHAT RE-ENTRY DOES</span>\n      <h1>After a market pullback, should you keep waiting—or put cash back into SPY/QQQ?</h1>\n      <p>This is not a stock picker or trading dashboard. It tells you when waiting after a market pullback may no longer be helping.</p>\n    </section>\n  );\n}\n'''
if helper not in page:
    if anchor not in page:
        raise SystemExit('StatusPill anchor missing')
    page = page.replace(anchor, helper, 1)

# Friendly dates in official/episode/intraday copy.
repls = {
    '{s.as_of} completed close': '{formatDate(s.as_of)} completed close',
    '<div><span className="kicker">CURRENT RE-ENTRY EPISODE</span><h2>{episode.episode_start}</h2></div>': '<div><span className="kicker">CURRENT RE-ENTRY EPISODE</span><h2>{formatDate(episode.episode_start)}</h2></div>',
    'The signal first fired on {episode.episode_start} and remained favorable through {episode.favorable_through}.': 'The signal first fired on {formatDate(episode.episode_start)} and remained favorable through {formatDate(episode.favorable_through)}.',
    '<em>{episode.episode_start}</em>': '<em>{formatDate(episode.episode_start)}</em>',
    'Last favorable close: <b>{episode.favorable_through}</b>': 'Last favorable close: <b>{formatDate(episode.favorable_through)}</b>',
    'changed on <b>{episode.ended_on}</b>': 'changed on <b>{formatDate(episode.ended_on)}</b>',
    '{` It does not replace the official ${official.as_of} close signal.`}': '{` It does not replace the official ${formatDate(official.as_of)} close signal.`}',
}
for a, b in repls.items():
    page = page.replace(a, b)

# Make the vehicle section explicitly the plain-English meaning of the decision.
page = page.replace('<div className="section-heading"><div><span className="kicker">WHERE IT APPLIES</span><h2>Broad-market re-entry</h2></div><StatusPill>SPY + QQQ</StatusPill></div>', '<div className="section-heading"><div><span className="kicker">WHAT THIS MEANS</span><h2>Broad-market re-entry</h2></div><StatusPill>SPY + QQQ</StatusPill></div>')
page = page.replace('The engine answers whether cash should go back into broad equities. SPY and QQQ are the validated destination set. Sector and subsector ETFs explain the setup but are not standalone buy calls.', 'The model currently answers whether continuing to wait after a pullback is still helping. When the answer is RE-ENTER, SPY and QQQ are the validated broad-market destination set. Sector and subsector ETFs explain the setup; they are not separate buy calls and this tool does not decide position size.')

# Fetch historical evidence with the existing page data.
old_fetch = 'const [snapshot, intraday, episode] = await Promise.all([getLatestSnapshot(), getIntradaySnapshot(), getLatestEpisode()]);'
new_fetch = 'const [snapshot, intraday, episode, historicalEvidence] = await Promise.all([getLatestSnapshot(), getIntradaySnapshot(), getLatestEpisode(), getHistoricalEpisodeEvidence()]);'
if old_fetch in page:
    page = page.replace(old_fetch, new_fetch, 1)
elif new_fetch not in page:
    raise SystemExit('Promise.all anchor missing')

# Rebuild main hierarchy. Keep all market rows visible through MarketMovementTables.
old_order = '''      <Hero s={s} />\n      <IntradayMonitor live={intraday} official={s} />\n      <WhyNow s={s} />\n      <EpisodeSummary episode={episode} official={s} />\n      <VehicleCard s={s} />\n      <Historical s={s} />\n      <OutperformanceCard />\n      <MarketMovementTables snapshot={s} live={intraday} />'''
new_order = '''      <ProductPurpose />\n      <Hero s={s} />\n      <VehicleCard s={s} />\n      <EpisodeSummary episode={episode} official={s} />\n      <WhyNow s={s} />\n      <div className="context-divider"><span className="kicker">WHAT IS HAPPENING TODAY · CONTEXT ONLY</span><p>Live movement helps explain what is happening underneath the official decision. It never replaces the completed-close RE-ENTRY signal.</p></div>\n      <IntradayMonitor live={intraday} official={s} />\n      <MarketMovementTables snapshot={s} live={intraday} />\n      <HistoricalEvidence evidence={historicalEvidence} />\n      <OutperformanceCard />'''
if old_order in page:
    page = page.replace(old_order, new_order, 1)
elif new_order not in page:
    raise SystemExit('Main render-order anchor missing')

page_path.write_text(page)

styles = '''\n/* Product purpose + full historical evidence */\n.purpose-card { margin-bottom: 16px; padding: 24px 28px; background: #f8f6f1; box-shadow: none; }\n.purpose-card h1 { margin: 7px 0 8px; max-width: 900px; font-size: clamp(25px, 3.4vw, 40px); line-height: 1.08; letter-spacing: -.045em; }\n.purpose-card p { margin: 0; max-width: 820px; color: var(--muted); font-size: 14px; line-height: 1.55; }\n.context-divider { margin: 28px 2px 4px; padding-top: 4px; }\n.context-divider p { margin: 7px 0 0; max-width: 820px; color: var(--muted); font-size: 12px; line-height: 1.5; }\n.history-summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); border-radius: 16px; overflow: hidden; margin-top: 18px; }\n.history-summary-grid > div { padding: 17px 16px; min-width: 0; }\n.history-summary-grid > div + div { border-left: 1px solid var(--line); }\n.history-summary-grid small, .history-summary-grid span { display: block; color: var(--muted); font-size: 9px; line-height: 1.35; }\n.history-summary-grid strong { display: block; margin: 7px 0 3px; font-size: 25px; letter-spacing: -.035em; font-variant-numeric: tabular-nums; }\n.history-subsection { margin-top: 28px; }\n.history-subheading { display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 8px; }\n.history-subheading h3 { margin: 4px 0 0; font-size: 17px; letter-spacing: -.025em; }\n.history-subheading > span, .history-note { color: var(--muted); font-size: 10px; }\n.history-note { max-width: 820px; margin: 0 0 12px; line-height: 1.5; }\n.episode-table-wrap { width: 100%; overflow-x: auto; border: 1px solid var(--line); border-radius: 14px; }\n.episode-table { min-width: 1080px; }\n.episode-head, .episode-row { display: grid; grid-template-columns: 1.15fr 1.15fr .55fr .62fr .62fr .8fr .8fr 1.5fr; gap: 12px; align-items: center; padding: 10px 13px; }\n.episode-head { background: #efede7; color: var(--muted); font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .05em; }\n.episode-row { border-top: 1px solid var(--line); font-size: 10px; }\n.episode-row > * { font-variant-numeric: tabular-nums; }\n.history-method { margin-top: 14px; color: var(--muted); font-size: 9px; }\n.history-method code { color: var(--ink); background: #efede7; padding: 2px 4px; border-radius: 4px; }\n@media (max-width: 760px) { .purpose-card { padding: 20px 17px; border-radius: 18px; } .history-summary-grid { grid-template-columns: 1fr 1fr; } .history-summary-grid > div:nth-child(3) { border-left: 0; border-top: 1px solid var(--line); } .history-summary-grid > div:nth-child(4) { border-top: 1px solid var(--line); } .history-subheading { align-items: flex-start; flex-direction: column; gap: 5px; } }\n'''
if '/* Product purpose + full historical evidence */' not in css:
    css += styles
css_path.write_text(css)
print('Applied product clarity and historical evidence UI patch')
