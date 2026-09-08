from pathlib import Path

p = Path('web/app/page.tsx')
s = p.read_text()
old = '''      <div className="vehicle-strip">\n        <div className="vehicle-primary"><div><span>S&P 500</span><b>SPY</b></div><small>Broad market</small><strong>{pct(h.SPY_10D_median_after_signal, 2)}</strong><em>10D historical median after RE-ENTRY signals</em></div>\n        <div className="vehicle-primary"><div><span>Nasdaq 100</span><b>QQQ</b></div><small>Growth heavy</small><strong>{pct(h.QQQ_10D_median_after_signal, 2)}</strong><em>10D historical median after RE-ENTRY signals</em></div>\n      </div>'''
new = '''      <div className="vehicle-strip">\n        <div className="vehicle-primary"><div><span>S&P 500</span><b>SPY</b></div><small>Validated broad-market destination</small><strong>Broad U.S. equities</strong><em>Historical performance is shown in the Historical Evidence section below.</em></div>\n        <div className="vehicle-primary"><div><span>Nasdaq 100</span><b>QQQ</b></div><small>Validated broad-market destination</small><strong>Growth-heavy equities</strong><em>Historical performance is shown in the Historical Evidence section below.</em></div>\n      </div>'''
if new not in s:
    if old not in s:
        raise SystemExit('Vehicle historical-metric block not found')
    s = s.replace(old, new, 1)
# historical_validation no longer needed locally in VehicleCard
s = s.replace('function VehicleCard({ s }: { s: ReentrySnapshot }) {\n  const h = s.historical_validation;\n', 'function VehicleCard({ s }: { s: ReentrySnapshot }) {\n')
p.write_text(s)
print('Moved vehicle historical metrics into Historical Evidence section')
