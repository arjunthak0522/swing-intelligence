"use client";

import { useEffect, useMemo, useState } from "react";

type BreadthResponse = {
  generated_at: string;
  source: string;
  source_cadence: string;
  nyse_advance_decline_volume_ratio: number | null;
  nasdaq_advance_decline_volume_ratio: number | null;
  nyse_trade_time?: string | null;
  nasdaq_trade_time?: string | null;
  errors?: string[];
};

const URL = "https://gexrdfzxmlnaawzmtlrk.supabase.co/functions/v1/reentry-market-breadth";

function splitRatio(ratio: number | null) {
  if (typeof ratio !== "number" || !Number.isFinite(ratio) || ratio < 0) return null;
  const advancing = ratio / (1 + ratio);
  return { advancing, declining: 1 - advancing };
}

function pct(value: number) {
  return `${(value * 100).toFixed(0)}%`;
}

function label(parts: ReturnType<typeof splitRatio>) {
  if (!parts) return "Unavailable";
  if (parts.declining >= 0.65) return "HEAVY SELLING";
  if (parts.declining >= 0.55) return "SELLING DOMINANT";
  if (parts.advancing >= 0.65) return "HEAVY BUYING";
  if (parts.advancing >= 0.55) return "BUYING DOMINANT";
  return "BALANCED";
}

export default function VolumeBreadthPanel({ compact = false }: { compact?: boolean }) {
  const [data, setData] = useState<BreadthResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetch(URL, { cache: "no-store" })
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((json) => { if (active) setData(json as BreadthResponse); })
      .catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, []);

  const nyse = useMemo(() => splitRatio(data?.nyse_advance_decline_volume_ratio ?? null), [data]);
  const nasdaq = useMemo(() => splitRatio(data?.nasdaq_advance_decline_volume_ratio ?? null), [data]);
  const unavailable = failed || (!nyse && !nasdaq);

  if (compact) {
    return <div className="volume-breadth-compact">
      <small>VOLUME BREADTH</small>
      <b className={unavailable ? "muted" : ((nyse?.declining ?? 0) > .55 || (nasdaq?.declining ?? 0) > .55 ? "bad-text" : "good-text")}>
        {unavailable ? "DATA SOURCE PENDING" : `${label(nyse)} / ${label(nasdaq)}`}
      </b>
    </div>;
  }

  return <div className="volume-breadth-panel">
    <div className="volume-breadth-row">
      <div><small>NYSE advancing volume</small><b>{nyse ? pct(nyse.advancing) : "-"}</b></div>
      <div><small>NYSE declining volume</small><b>{nyse ? pct(nyse.declining) : "-"}</b></div>
    </div>
    <div className="volume-breadth-row">
      <div><small>Nasdaq advancing volume</small><b>{nasdaq ? pct(nasdaq.advancing) : "-"}</b></div>
      <div><small>Nasdaq declining volume</small><b>{nasdaq ? pct(nasdaq.declining) : "-"}</b></div>
    </div>
    <p className="volume-breadth-note">
      {unavailable
        ? "Reliable advancing/declining volume is not available from the current free feed, so RE-ENTRY is intentionally not substituting sector or subsector percentages."
        : "Percentages are advancing vs declining share volume within each exchange. A larger declining share means trading activity is concentrated in falling stocks."}
    </p>
    <style jsx>{`
      .volume-breadth-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.volume-breadth-row>div{padding:12px;background:#f4f1eb;border-radius:10px}.volume-breadth-row small,.volume-breadth-row b{display:block}.volume-breadth-row small{font-size:9px;color:var(--muted)}.volume-breadth-row b{margin-top:3px;font-size:20px}.volume-breadth-note{margin:10px 0 0;font-size:10px;color:var(--muted);line-height:1.5}.volume-breadth-compact small,.volume-breadth-compact b{display:block}.volume-breadth-compact small{font-size:9px;color:var(--muted);margin-bottom:4px}.volume-breadth-compact b{font-size:11px}@media(max-width:760px){.volume-breadth-row{grid-template-columns:1fr 1fr}}
    `}</style>
  </div>;
}
