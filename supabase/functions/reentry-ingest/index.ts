import { createClient } from "npm:@supabase/supabase-js@2";
import { createRemoteJWKSet, jwtVerify } from "npm:jose@6";

const cors = {
  "content-type": "application/json",
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type",
};

const jwks = createRemoteJWKSet(new URL("https://token.actions.githubusercontent.com/.well-known/jwks"));
const EXPECTED_REPO = "arjunthak0522/swing-intelligence";
const EXPECTED_AUD = "reentry-supabase";

function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const obj = value as Record<string, unknown>;
  return `{${Object.keys(obj).sort().map((k) => `${JSON.stringify(k)}:${canonical(obj[k])}`).join(",")}}`;
}

async function sha256(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(value));
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(hash)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function authorize(req: Request) {
  const auth = req.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!token) throw new Error("missing GitHub OIDC token");
  const { payload } = await jwtVerify(token, jwks, {
    issuer: "https://token.actions.githubusercontent.com",
    audience: EXPECTED_AUD,
  });
  if (payload.repository !== EXPECTED_REPO) throw new Error("unexpected repository");
  if (payload.ref !== "refs/heads/main") throw new Error("writes only allowed from main");
  return payload;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return new Response(JSON.stringify({ error: "POST required" }), { status: 405, headers: cors });
  try {
    await authorize(req);
    const body = await req.json();
    const snapshot = body?.snapshot;
    const realized = body?.realized ?? { outcomes: {} };
    if (!snapshot?.as_of || !snapshot?.engine_version || !Array.isArray(snapshot?.analogs)) {
      return new Response(JSON.stringify({ error: "invalid payload" }), { status: 400, headers: cors });
    }
    if (snapshot.analogs.length !== 40) {
      return new Response(JSON.stringify({ error: "expected exactly 40 analogs" }), { status: 400, headers: cors });
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL")!,
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
      { auth: { persistSession: false } },
    );
    const payloadHash = await sha256(snapshot);

    const { data: existing, error: existingError } = await supabase
      .from("reentry_daily_snapshots")
      .select("payload_hash")
      .eq("as_of", snapshot.as_of)
      .maybeSingle();
    if (existingError) throw existingError;
    if (existing && existing.payload_hash !== payloadHash) {
      return new Response(JSON.stringify({ error: "immutable snapshot conflict", as_of: snapshot.as_of }), { status: 409, headers: cors });
    }

    if (!existing) {
      const { error } = await supabase.from("reentry_daily_snapshots").insert({
        as_of: snapshot.as_of,
        engine_version: snapshot.engine_version,
        schema_version: snapshot.schema_version,
        signal: snapshot.signal,
        analog_decision: snapshot.analog_decision,
        market_state: snapshot.market_state,
        weakness_present: snapshot.weakness_present,
        payload_hash: payloadHash,
        payload: snapshot,
      });
      if (error) throw error;

      const analogRows = snapshot.analogs.map((a: any) => ({
        signal_date: snapshot.as_of,
        rank: a.rank,
        analog_date: a.date,
        distance: a.distance,
        engine_version: snapshot.engine_version,
      }));
      const { error: analogError } = await supabase.from("reentry_analogs").insert(analogRows);
      if (analogError) throw analogError;
    }

    let insertedRealized = 0;
    for (const symbol of ["SPY", "QQQ"]) {
      for (const [horizon, outcome] of Object.entries(realized?.outcomes?.[symbol] ?? {})) {
        const row: any = outcome;
        const key = { signal_date: snapshot.as_of, symbol, horizon: Number(horizon) };
        const { data: prior, error: priorError } = await supabase
          .from("reentry_realized_outcomes")
          .select("realized_return,max_drawdown,exit_date")
          .match(key)
          .maybeSingle();
        if (priorError) throw priorError;
        if (prior) {
          const same = Math.abs(prior.realized_return - row.realized_return) < 1e-12 &&
            Math.abs(prior.max_drawdown - row.max_drawdown) < 1e-12 && prior.exit_date === row.exit_date;
          if (!same) return new Response(JSON.stringify({ error: "immutable realized outcome conflict", ...key }), { status: 409, headers: cors });
          continue;
        }
        const { error } = await supabase.from("reentry_realized_outcomes").insert({
          ...key,
          engine_version: snapshot.engine_version,
          entry_date: row.entry_date,
          exit_date: row.exit_date,
          entry_close: row.entry_close,
          exit_close: row.exit_close,
          realized_return: row.realized_return,
          max_drawdown: row.max_drawdown,
          max_favorable_excursion: row.max_favorable_excursion,
          round_trip_cost: row.round_trip_cost,
        });
        if (error) throw error;
        insertedRealized += 1;
      }
    }

    return new Response(JSON.stringify({ ok: true, as_of: snapshot.as_of, snapshot_inserted: !existing, realized_inserted: insertedRealized }), { headers: cors });
  } catch (error) {
    return new Response(JSON.stringify({ error: String(error) }), { status: 401, headers: cors });
  }
});
