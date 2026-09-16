import { Activity, CalendarDays, ShieldCheck } from "lucide-react";
import type { WashoutSnapshot } from "../lib/reentry";

export default function ReentryOpportunityWindow({washout}:{washout:WashoutSnapshot}) {
  const u = washout.unified_engine;
  if (!u) return null;
  const active = Boolean(u.reentry_window_active);
  const age = u.reentry_window_age_sessions;
  const horizon = u.reentry_window_researched_sessions ?? 30;
  const beyond = u.reentry_window_research_status === "BEYOND_RESEARCHED_HORIZON";
  return <section className={`opportunity-window ${active ? "active" : "inactive"}`}>
    <div className="window-icon"><Activity size={20}/></div>
    <div className="window-copy">
      <span className="kicker">OPPORTUNITY WINDOW</span>
      <h2>{active ? "RE-ENTRY WINDOW ACTIVE" : "NO ACTIVE RE-ENTRY WINDOW"}</h2>
      <p>{u.reentry_window_reason || "Persistent re-entry context is unavailable."}</p>
    </div>
    <div className="window-meta">
      <span><CalendarDays size={14}/><small>Opened</small><b>{u.reentry_window_trigger_date || "-"}</b></span>
      <span><ShieldCheck size={14}/><small>Age</small><b>{typeof age === "number" ? `${age} session${age === 1 ? "" : "s"}` : "-"}</b></span>
      <span><small>Research</small><b>{beyond ? `Beyond ${horizon}-session study` : active ? `Supported through ${horizon} sessions` : "Not started"}</b></span>
    </div>
  </section>;
}
