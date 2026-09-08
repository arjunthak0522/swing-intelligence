from pathlib import Path

page = Path('web/app/page.tsx')
text = page.read_text()
needle = 'import { ChevronRight, CircleAlert, CircleCheck, Clock3, Radio } from "lucide-react";\n'
insert = needle + 'import MarketMovementTables from "./MarketMovementTables";\n'
if 'import MarketMovementTables from "./MarketMovementTables";' not in text:
    if needle not in text:
        raise SystemExit('page import anchor not found')
    text = text.replace(needle, insert, 1)
old = '      <SectorMap s={s} />\n      <MarketInternals s={s} />'
new = '      <MarketMovementTables snapshot={s} live={intraday} />'
if old not in text and new not in text:
    raise SystemExit('market table render anchor not found')
text = text.replace(old, new, 1)
page.write_text(text)

css = Path('web/app/globals.css')
styles = css.read_text()
marker = '/* market-sort-controls */'
block = r'''

/* market-sort-controls */
.sort-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; margin: 0 0 15px; }
.sort-bar > span { color: var(--muted); font-size: 10px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; margin-right: 2px; }
.sort-chip { border: 1px solid var(--line); background: #f1efe9; color: var(--muted); border-radius: 999px; padding: 6px 10px; font-size: 10px; font-weight: 750; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; }
.sort-chip:hover { border-color: #c9c4b8; color: var(--ink); }
.sort-chip.active { background: var(--ink); color: #fff; border-color: var(--ink); }
.sort-chip svg { transition: transform .15s ease; }
.sort-chip .sort-up { transform: rotate(180deg); }
.sector-table-head.sector-move-head, .sector-table-row.sector-move-row { grid-template-columns: 1.45fr .55fr .7fr .9fr .85fr; }
.subsector-head { display: grid; grid-template-columns: minmax(250px, 1.4fr) .55fr .55fr .75fr .9fr 22px; align-items: center; gap: 14px; padding: 10px 2px 8px; border-top: 1px solid var(--line); color: var(--muted); font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; }
.movement-row summary { display: grid; grid-template-columns: minmax(250px, 1.4fr) minmax(420px, 2.75fr); }
.movement-metrics { display: grid; grid-template-columns: .55fr .55fr .75fr .9fr 22px; align-items: center; gap: 14px; font-size: 11px; font-variant-numeric: tabular-nums; text-align: right; }
.movement-metrics b { font-size: 9px; letter-spacing: .04em; }
@media (max-width: 760px) {
  .sort-bar { margin-bottom: 10px; }
  .sector-table-row.sector-move-row { grid-template-columns: 1.25fr .55fr .7fr; }
  .sector-table-row.sector-move-row > span:nth-of-type(1) { display: block; }
  .sector-table-row.sector-move-row > span:nth-of-type(2) { display: none; }
  .sector-table-row.sector-move-row > span:nth-of-type(3) { display: none; }
  .subsector-head { grid-template-columns: minmax(150px, 1.4fr) .6fr .6fr .75fr; }
  .subsector-head span:nth-child(5), .subsector-head span:nth-child(6) { display: none; }
  .movement-row summary { grid-template-columns: minmax(150px, 1.4fr) minmax(160px, 1.6fr); gap: 8px; }
  .movement-metrics { grid-template-columns: .6fr .6fr .75fr; gap: 8px; }
  .movement-metrics b, .movement-metrics svg { display: none; }
}
'''
if marker not in styles:
    styles += block
css.write_text(styles)
