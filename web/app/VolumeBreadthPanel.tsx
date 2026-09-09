"use client";

import { useEffect, useState } from "react";

type ExchangeBreadth = {
  net_advancing_volume: number | null;
  advancing_volume: number | null;
  declining_volume: number | null;
  advancing_volume_share: number | null;
  declining_volume_share: number | null;
  down_up_volume_ratio: number | null;
  pressure: string;
  as_of: string | null;
};

type BreadthResponse = {
  generated_at: string;
  source: string;
  source_note?: string;
  nyse?: ExchangeBreadth;
  nasdaq?: ExchangeBreadth;
  errors?: string[];
};

const URL = "https://gexrdfzxmlnaawzmtlrk.supabase.co/functions/v1/reentry-market-breadth";

function pct(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(0)}%` : "-";
}

function ratio(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)}x` : "-";
}

function pressureClass(value?: string | null) {
  const v = (value ?? "").toUpperCase();
  if (v.includes("SELLING")) return "bad-text";
  if (v.includes("BUYING")) return "good-text";
  return "muted";
}

function compactLabel(data: BreadthResponse | null) {
  if (!data?.nyse || !data?.nasdaq) return "DATA UNAVAILABLE";
  return `NYSE ${pct(data.nyse.declining_volume_share)} down / Nasdaq ${pct(data.nasdaq.declining_volume_share)} down`;
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

  const unavailable = failed || !data?.nyse || !data?.nasdaq;

  if (compact) {
    return <div className="volume-breadth-compact">
      <small>VOLUME BREADTH</small>
      <b className={unavailable ? "muted" : ((data?.nyse?.declining_volume_share ?? 0) > .55 || (data?.nasdaq?.declining_volume_share ?? 0) > .55 ? "bad-text" : "good-text")}>
        {unavailable ? "DATA UNAVAILABLE" : compactLabel(data)}
      </b>
    </div>;
  }

  return <div className="volume-breadth-panel">
    <div className="volume-exchange-grid">
      <section>
        <div className="volume-exchange-head"><span>NYSE</span><b className={pressureClass(data?.nyse?.pressure)}>{data?.nyse?.pressure ?? "Unavailable"}</b></div>
        <div className="volume-breadth-row">
          <div><small>Advancing volume</small><b>{pct(data?.nyse?.advancing_volume_share)}</b></div>
          <div><small>Declining volume</small><b>{pct(data?.nyse?.declining_volume_share)}</b></div>
          <div><small>Down / up ratio</small><b>{ratio(data?.nyse?.down_up_volume_ratio)}</b></div>
        </div>
      </section>
      <section>
        <div className="volume-exchange-head"><span>NASDAQ</span><b className={pressureClass(data?.nasdaq?.pressure)}>{data?.nasdaq?.pressure ?? "Unavailable"}</b></div>
        <div className="volume-breadth-row">
          <div><small>Advancing volume</small><b>{pct(data?.nasdaq?.advancing_volume_share)}</b></div>
          <div><small>Declining volume</small><b>{pct(data?.nasdaq?.declining_volume_share)}</b></div>
          <div><small>Down / up ratio</small><b>{ratio(data?.nasdaq?.down_up_volume_ratio)}</b></div>
        </div>
      </section>
    </div>
    <p className="volume-breadth-note">
      {unavailable
        ? "StockCharts volume-breadth data is temporarily unavailable. RE-ENTRY will not substitute sector or subsector percentages."
        : <>Source: StockCharts delayed breadth symbols $NYUD / $NAUD plus $NYUPV / $NYDNV / $NAUPV / $NADNV. Percentages show where advancing vs declining share volume is concentrated. Latest breadth timestamps: NYSE {data?.nyse?.as_of ?? "-"}, Nasdaq {data?.nasdaq?.as_of ?? "-"} ET.</>}
    </p>
    <style jsx>{`
      .volume-exchange-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}.volume-exchange-grid>section{padding:12px;background:#f4f1eb;border-radius:12px}.volume-exchange-head{display:flex;align-items:center;justify-content:space-between;gap:10px}.volume-exchange-head span{font-size:10px;font-weight:900;letter-spacing:.04em}.volume-exchange-head b{font-size:10px}.volume-breadth-row{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.volume-breadth-row>div{padding-top:8px;border-top:1px solid var(--line)}.volume-breadth-row small,.volume-breadth-row b{display:block}.volume-breadth-row small{font-size:8px;color:var(--muted)}.volume-breadth-row b{margin-top:3px;font-size:18px}.volume-breadth-note{margin:10px 0 0;font-size:9px;color:var(--muted);line-height:1.5}.volume-breadth-compact small,.volume-breadth-compact b{display:block}.volume-breadth-compact small{font-size:9px;color:var(--muted);margin-bottom:4px}.volume-breadth-compact b{font-size:11px}@media(max-width:760px){.volume-exchange-grid{grid-template-columns:1fr}.volume-breadth-row{grid-template-columns:repeat(3,1fr)}}
    `}</style>
  </div>;
}
