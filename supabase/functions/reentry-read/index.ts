import { createClient } from "npm:@supabase/supabase-js@2";

const headers = {
  "content-type": "application/json",
  "access-control-allow-origin": "*",
  "cache-control": "public, max-age=60, s-maxage=300",
};

function respond(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers });
}

Deno.serve(async (req) => {
  if (req.method !== "GET") return respond({ error: "GET required" }, 405);
  const url = new URL(req.url);
  const resource = url.searchParams.get("resource") ?? "latest";
  const date = url.searchParams.get("date");
  const limit = Math.min(Math.max(Number(url.searchParams.get("limit") ?? 100), 1), 500);

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
    { auth: { persistSession: false } },
  );

  try {
    if (resource === "latest") {
      const { data, error } = await supabase
        .from("reentry_daily_snapshots")
        .select("payload")
        .order("as_of", { ascending: false })
        .limit(1)
        .maybeSingle();
      if (error) throw error;
      return respond(data?.payload ?? null);
    }

    if (resource === "snapshot") {
      if (!date) return respond({ error: "date required" }, 400);
      const { data, error } = await supabase
        .from("reentry_daily_snapshots")
        .select("payload")
        .eq("as_of", date)
        .maybeSingle();
      if (error) throw error;
      return respond(data?.payload ?? null, data ? 200 : 404);
    }

    if (resource === "history") {
      const { data, error } = await supabase
        .from("reentry_daily_snapshots")
        .select("as_of,engine_version,signal,analog_decision,market_state,weakness_present,created_at")
        .order("as_of", { ascending: false })
        .limit(limit);
      if (error) throw error;
      return respond(data ?? []);
    }

    if (resource === "analogs") {
      if (!date) return respond({ error: "date required" }, 400);
      const { data, error } = await supabase
        .from("reentry_analogs")
        .select("rank,analog_date,distance,engine_version")
        .eq("signal_date", date)
        .order("rank", { ascending: true });
      if (error) throw error;
      return respond(data ?? []);
    }

    if (resource === "realized") {
      if (!date) return respond({ error: "date required" }, 400);
      const { data, error } = await supabase
        .from("reentry_realized_outcomes")
        .select("signal_date,symbol,horizon,entry_date,exit_date,entry_close,exit_close,realized_return,max_drawdown,max_favorable_excursion,round_trip_cost")
        .eq("signal_date", date)
        .order("symbol", { ascending: true })
        .order("horizon", { ascending: true });
      if (error) throw error;
      return respond(data ?? []);
    }

    return respond({ error: "unknown resource" }, 400);
  } catch (error) {
    return respond({ error: String(error) }, 500);
  }
});
