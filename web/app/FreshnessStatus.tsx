import { getLatestSnapshot } from "../lib/reentry";

type RetailMetadata = {
  published_at_utc?: string;
  feed_mode?: string;
};

function formatPublished(value?: string) {
  if (!value) return "Publish time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Publish time unavailable";
  return date.toLocaleString("en-US", {
    timeZone: "America/New_York",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export default async function FreshnessStatus() {
  const snapshot = await getLatestSnapshot();
  if (!snapshot) {
    return (
      <div style={{ margin: "0 auto 14px", maxWidth: 1180, padding: "0 20px" }}>
        <div className="notice"><b>DATA INCOMPLETE</b> · No completed-close snapshot is available. Do not treat any prior signal as current.</div>
      </div>
    );
  }

  const metadata = (snapshot as typeof snapshot & { retail_metadata?: RetailMetadata }).retail_metadata;
  const complete = snapshot.data_freshness?.same_day_complete === true;

  return (
    <div style={{ margin: "0 auto 14px", maxWidth: 1180, padding: "0 20px" }}>
      <div className="notice" style={{ justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span><b>{complete ? "DATA COMPLETE" : "DATA INCOMPLETE"}</b> · Official decision uses the {snapshot.as_of} completed close.</span>
        <span>{formatPublished(metadata?.published_at_utc)} · {metadata?.feed_mode === "COMPLETED_CLOSE_ONLY" ? "Completed-close feed" : "Close feed"}</span>
      </div>
    </div>
  );
}
