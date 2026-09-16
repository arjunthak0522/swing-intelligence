from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Expected source block not found in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Canonical engine: add separate persistent re-entry window metadata.
engine = ROOT / "tools/reentry_unified_engine.py"
replace_once(
    engine,
    'FAST_FAMILY_MEMORY_MINUTES = 30\n',
    'FAST_FAMILY_MEMORY_MINUTES = 30\nREENTRY_WINDOW_RESEARCHED_SESSIONS = 30\n',
)
replace_once(
    engine,
    '''def load_prior(market_date: str) -> dict | None:\n    rows = load_day_rows(market_date)\n    return rows[-1] if rows else None\n\n\ndef first_latched_go''',
    '''def load_prior(market_date: str) -> dict | None:\n    rows = load_day_rows(market_date)\n    return rows[-1] if rows else None\n\n\ndef load_history_rows() -> list[dict]:\n    if not HISTORY.exists():\n        return []\n    with HISTORY.open(newline="", encoding="utf-8") as f:\n        rows = list(csv.DictReader(f))\n    rows.sort(key=lambda r: (r.get("market_date") or "", r.get("timestamp_et") or ""))\n    return rows\n\n\ndef reentry_window_state(market_date: str, deployment_signal: str) -> dict:\n    rows = load_history_rows()\n    deploy_rows = [\n        r for r in rows\n        if (r.get("deployment_signal") == "DEPLOY" or (r.get("decision") or r.get("state")) == "GO_EARLY")\n        and (r.get("market_date") or "") <= market_date\n    ]\n\n    fresh_trigger_today = deployment_signal == "DEPLOY"\n    trigger_date = market_date if fresh_trigger_today else (deploy_rows[-1].get("market_date") if deploy_rows else None)\n    active = bool(trigger_date)\n\n    if active:\n        observed_sessions = sorted({\n            r.get("market_date") for r in rows\n            if r.get("market_date") and trigger_date <= r.get("market_date") <= market_date\n        })\n        if market_date not in observed_sessions:\n            observed_sessions.append(market_date)\n            observed_sessions.sort()\n        age_sessions = max(0, len(observed_sessions) - 1)\n        research_status = (\n            "SUPPORTED_WITHIN_RESEARCH_HORIZON"\n            if age_sessions <= REENTRY_WINDOW_RESEARCHED_SESSIONS\n            else "BEYOND_RESEARCHED_HORIZON"\n        )\n        if fresh_trigger_today:\n            reason = "A qualifying DEPLOY fired today, opening a favorable re-entry opportunity. The canonical signal remains the decision source; this window is persistent context only."\n        else:\n            reason = "A prior DEPLOY opened a favorable re-entry opportunity. Historical research found persistence through at least 30 sessions and did not validate a normalization-based automatic exit, so the window remains active."\n    else:\n        age_sessions = None\n        research_status = "NOT_STARTED"\n        reason = "No prior DEPLOY has opened a persistent re-entry opportunity in the available canonical history."\n\n    return {\n        "reentry_window_active": active,\n        "reentry_window_trigger_date": trigger_date,\n        "reentry_window_age_sessions": age_sessions,\n        "reentry_window_researched_sessions": REENTRY_WINDOW_RESEARCHED_SESSIONS,\n        "reentry_window_research_status": research_status,\n        "reentry_window_fresh_trigger_today": fresh_trigger_today,\n        "reentry_window_reason": reason,\n        "reentry_window_is_decision_input": False,\n    }\n\n\ndef first_latched_go''',
)
replace_once(
    engine,
    '''    result = evaluate(payload, prior, recent, latched_go)\n    result["market_phase"] = market_phase(now)\n''',
    '''    result = evaluate(payload, prior, recent, latched_go)\n    result.update(reentry_window_state(market_date, result["deployment_signal"]))\n    result["market_phase"] = market_phase(now)\n''',
)
replace_once(
    engine,
    '''        "go_triggered_at_et": result["go_triggered_at_et"],\n        "oversold_gate": int(result["oversold_gate"]),\n''',
    '''        "go_triggered_at_et": result["go_triggered_at_et"],\n        "reentry_window_active": int(result["reentry_window_active"]),\n        "reentry_window_trigger_date": result["reentry_window_trigger_date"],\n        "reentry_window_age_sessions": result["reentry_window_age_sessions"],\n        "reentry_window_research_status": result["reentry_window_research_status"],\n        "oversold_gate": int(result["oversold_gate"]),\n''',
)

# 2) Frontend types.
reentry = ROOT / "web/lib/reentry.ts"
replace_once(
    reentry,
    '''    actionable?: boolean;\n  };\n}\n''',
    '''    actionable?: boolean;\n    reentry_window_active?: boolean;\n    reentry_window_trigger_date?: string | null;\n    reentry_window_age_sessions?: number | null;\n    reentry_window_researched_sessions?: number | null;\n    reentry_window_research_status?: string | null;\n    reentry_window_fresh_trigger_today?: boolean;\n    reentry_window_reason?: string | null;\n    reentry_window_is_decision_input?: boolean;\n  };\n}\n''',
)

# 3) New premium opportunity-window component.
window_component = ROOT / "web/app/ReentryOpportunityWindow.tsx"
window_component.write_text('''import { Activity, CalendarDays, ShieldCheck } from "lucide-react";\nimport type { WashoutSnapshot } from "../lib/reentry";\n\nexport default function ReentryOpportunityWindow({washout}:{washout:WashoutSnapshot}) {\n  const u = washout.unified_engine;\n  if (!u) return null;\n  const active = Boolean(u.reentry_window_active);\n  const age = u.reentry_window_age_sessions;\n  const horizon = u.reentry_window_researched_sessions ?? 30;\n  const beyond = u.reentry_window_research_status === "BEYOND_RESEARCHED_HORIZON";\n  return <section className={`opportunity-window ${active ? "active" : "inactive"}`}>\n    <div className="window-icon"><Activity size={20}/></div>\n    <div className="window-copy">\n      <span className="kicker">OPPORTUNITY WINDOW</span>\n      <h2>{active ? "RE-ENTRY WINDOW ACTIVE" : "NO ACTIVE RE-ENTRY WINDOW"}</h2>\n      <p>{u.reentry_window_reason || "Persistent re-entry context is unavailable."}</p>\n    </div>\n    <div className="window-meta">\n      <span><CalendarDays size={14}/><small>Opened</small><b>{u.reentry_window_trigger_date || "-"}</b></span>\n      <span><ShieldCheck size={14}/><small>Age</small><b>{typeof age === "number" ? `${age} session${age === 1 ? "" : "s"}` : "-"}</b></span>\n      <span><small>Research</small><b>{beyond ? `Beyond ${horizon}-session study` : active ? `Supported through ${horizon} sessions` : "Not started"}</b></span>\n    </div>\n  </section>;\n}\n''', encoding="utf-8")

# 4) Page hierarchy: decision -> window -> historical edge -> current evidence -> deep diagnostics.
page = ROOT / "web/app/page.tsx"
replace_once(
    page,
    'import AggregateHistoricalEvidence from "./AggregateHistoricalEvidence";\n',
    'import AggregateHistoricalEvidence from "./AggregateHistoricalEvidence";\nimport ReentryOpportunityWindow from "./ReentryOpportunityWindow";\n',
)
replace_once(
    page,
    '''  extension_signal_count?: number;\n  weak_signal_count?: number;\n};\n''',
    '''  extension_signal_count?: number;\n  weak_signal_count?: number;\n  reentry_window_active?: boolean;\n  reentry_window_trigger_date?: string|null;\n  reentry_window_age_sessions?: number|null;\n  reentry_window_research_status?: string|null;\n  reentry_window_reason?: string|null;\n};\n''',
)
replace_once(
    page,
    '<span className="eyebrow">SPARE CASH SIGNAL</span>',
    '<span className="eyebrow">TODAY\'S CASH SIGNAL</span>',
)
replace_once(
    page,
    '''      <UnifiedHero washout={washout}/>\n      <MarketContext live={intraday} washout={washout}/>\n      <SecondaryConfirmation washout={washout}/>\n      <LeadingIndicators washout={washout}/>\n      <AggregateHistoricalEvidence evidence={historical} cashPolicy={cashPolicy} currentAction={currentAction} currentCondition={currentCondition}/>\n      <ReentryDecisionDetails washout={washout}/>\n      {snapshot?<MarketMovementTables snapshot={snapshot} live={intraday}/>:<section className="card section-card"><div className="notice"><CircleAlert size={16}/> Sector and subsector context unavailable.</div></section>}\n''',
    '''      <div className="priority-stack">\n        <UnifiedHero washout={washout}/>\n        <ReentryOpportunityWindow washout={washout}/>\n      </div>\n      <div className="tier-label"><span>HISTORICAL EDGE</span><p>What happened after comparable re-entry opportunities.</p></div>\n      <AggregateHistoricalEvidence evidence={historical} cashPolicy={cashPolicy} currentAction={currentAction} currentCondition={currentCondition}/>\n      <div className="tier-label"><span>CURRENT MARKET EVIDENCE</span><p>What today\'s internals say about the quality and maturity of the setup.</p></div>\n      <MarketContext live={intraday} washout={washout}/>\n      <SecondaryConfirmation washout={washout}/>\n      <LeadingIndicators washout={washout}/>\n      <details className="diagnostics-shell">\n        <summary><span>DEEP DIAGNOSTICS</span><small>Engine inputs, reversal families, sectors and subsectors</small></summary>\n        <ReentryDecisionDetails washout={washout}/>\n        {snapshot?<MarketMovementTables snapshot={snapshot} live={intraday}/>:<section className="card section-card"><div className="notice"><CircleAlert size={16}/> Sector and subsector context unavailable.</div></section>}\n      </details>\n''',
)
replace_once(
    page,
    'Market-condition, recovery-stage, secondary-confirmation, and leading-indicator labels are descriptive context and never create a second decision engine.',
    'RE-ENTRY WINDOW is persistent opportunity context only and never creates or overrides a DEPLOY signal. Market-condition, recovery-stage, secondary-confirmation, and leading-indicator labels are descriptive context and never create a second decision engine.',
)

# 5) Premium fintech styling, consolidated into a small additive file.
overrides = ROOT / "web/app/retail-overrides.css"
overrides.write_text('''/* Premium fintech information architecture layer */\n.priority-stack{display:grid;gap:14px;margin-bottom:28px}.opportunity-window{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:16px;align-items:center;padding:18px 20px;border:1px solid rgba(29,78,216,.16);border-radius:18px;background:linear-gradient(135deg,rgba(239,246,255,.96),rgba(255,255,255,.98));box-shadow:0 12px 28px rgba(15,23,42,.055)}.opportunity-window.active{border-color:rgba(37,99,235,.28);background:linear-gradient(135deg,rgba(239,246,255,.98),rgba(248,250,252,.98))}.window-icon{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;background:#0f172a;color:white}.window-copy h2{margin:3px 0 5px;font-size:20px;letter-spacing:-.02em}.window-copy p{margin:0;max-width:760px;color:var(--muted);line-height:1.5}.window-meta{display:flex;gap:10px;flex-wrap:wrap;justify-content:flex-end}.window-meta span{min-width:120px;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.82);border:1px solid rgba(15,23,42,.07);display:grid;grid-template-columns:auto 1fr;column-gap:7px;align-items:center}.window-meta small{font-size:9px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}.window-meta b{grid-column:1/-1;margin-top:3px;font-size:11px}.tier-label{display:flex;align-items:baseline;gap:12px;margin:34px 2px 12px}.tier-label span{font-size:10px;font-weight:800;letter-spacing:.16em}.tier-label p{margin:0;color:var(--muted);font-size:11px}.diagnostics-shell{margin-top:34px;border-top:1px solid rgba(15,23,42,.1);padding-top:8px}.diagnostics-shell>summary{cursor:pointer;list-style:none;display:flex;justify-content:space-between;align-items:center;padding:14px 2px;color:var(--muted)}.diagnostics-shell>summary::-webkit-details-marker{display:none}.diagnostics-shell>summary span{font-size:10px;font-weight:800;letter-spacing:.14em;color:var(--text)}.diagnostics-shell>summary small{font-size:10px}.diagnostics-shell[open]>summary{margin-bottom:8px}@media(max-width:760px){.opportunity-window{grid-template-columns:1fr;padding:16px}.window-icon{display:none}.window-meta{justify-content:flex-start}.window-meta span{flex:1;min-width:0}.tier-label{display:block}.tier-label p{margin-top:4px}.diagnostics-shell>summary{align-items:flex-start;gap:8px;flex-direction:column}}\n''', encoding="utf-8")

# 6) Focused regression tests for persistent window semantics.
test = ROOT / "tests/test_reentry_window_state.py"
test.write_text('''import csv\nimport importlib.util\nfrom pathlib import Path\n\nMODULE_PATH = Path(__file__).resolve().parents[1] / "tools/reentry_unified_engine.py"\nspec = importlib.util.spec_from_file_location("reentry_unified_engine", MODULE_PATH)\nengine = importlib.util.module_from_spec(spec)\nassert spec and spec.loader\nspec.loader.exec_module(engine)\n\n\ndef write_history(path, rows):\n    fields = ["market_date", "timestamp_et", "decision", "deployment_signal"]\n    with path.open("w", newline="", encoding="utf-8") as f:\n        w = csv.DictWriter(f, fieldnames=fields)\n        w.writeheader()\n        w.writerows(rows)\n\n\ndef test_fresh_deploy_opens_window(tmp_path, monkeypatch):\n    monkeypatch.setattr(engine, "HISTORY", tmp_path / "history.csv")\n    state = engine.reentry_window_state("2026-09-16", "DEPLOY")\n    assert state["reentry_window_active"] is True\n    assert state["reentry_window_trigger_date"] == "2026-09-16"\n    assert state["reentry_window_age_sessions"] == 0\n    assert state["reentry_window_is_decision_input"] is False\n\n\ndef test_prior_deploy_keeps_window_active_without_new_trigger(tmp_path, monkeypatch):\n    history = tmp_path / "history.csv"\n    write_history(history, [\n        {"market_date":"2026-09-14","timestamp_et":"2026-09-14T15:00:00-04:00","decision":"GO_EARLY","deployment_signal":"DEPLOY"},\n        {"market_date":"2026-09-15","timestamp_et":"2026-09-15T15:00:00-04:00","decision":"WATCH","deployment_signal":"WATCH"},\n    ])\n    monkeypatch.setattr(engine, "HISTORY", history)\n    state = engine.reentry_window_state("2026-09-16", "WATCH")\n    assert state["reentry_window_active"] is True\n    assert state["reentry_window_trigger_date"] == "2026-09-14"\n    assert state["reentry_window_age_sessions"] == 2\n    assert state["reentry_window_research_status"] == "SUPPORTED_WITHIN_RESEARCH_HORIZON"\n\n\ndef test_window_does_not_invent_expiry_beyond_researched_horizon(tmp_path, monkeypatch):\n    history = tmp_path / "history.csv"\n    rows = []\n    for i in range(32):\n        rows.append({"market_date":f"2026-08-{i+1:02d}","timestamp_et":"x","decision":"WAIT","deployment_signal":"HOLD_CASH"})\n    rows[0]["decision"] = "GO_EARLY"\n    rows[0]["deployment_signal"] = "DEPLOY"\n    write_history(history, rows)\n    monkeypatch.setattr(engine, "HISTORY", history)\n    state = engine.reentry_window_state("2026-09-16", "WATCH")\n    assert state["reentry_window_active"] is True\n    assert state["reentry_window_research_status"] == "BEYOND_RESEARCHED_HORIZON"\n''', encoding="utf-8")

print("Applied persistent re-entry window and fintech hierarchy changes.")
