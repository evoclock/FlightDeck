// ---- API routes, appended by site/build.py after worker.template.js (which is left unchanged). ----
// Every /api/* request passes the same Access check as the page: CFG, verify() and deny() above.
//   POST /api/responses  stores decision and step responses in KV FLIGHTDECK_RESPONSES.
//   POST /api/chat-accept  merges one chat Accept, Reject, or comment into KV without wiping other answers.
//   GET  /api/spark      returns the latest cluster reading from KV FLIGHTDECK_SPARK (key "spark/latest").
//   POST /api/spark      stores a reading shaped like data.json `spark` in KV FLIGHTDECK_SPARK.
// Without the binding a route answers 501 and the page keeps its local copy or rendered snapshot.
const MAX_BODY = 65536;
const json = (status, obj) =>
  new Response(JSON.stringify(obj), { status, headers: { ...HDRS, "content-type": "application/json; charset=utf-8" } });

async function access(req) {
  if (!CFG.team || !CFG.aud) return { res: deny("Not available.") };
  const tok = req.headers.get("cf-access-jwt-assertion");
  let claims = null;
  try { claims = tok ? await verify(tok) : null; } catch (_) { claims = null; }
  if (!claims) return { res: deny("Forbidden.") };
  return { claims };
}

async function readBody(req) {
  const origin = req.headers.get("origin");
  if (origin && origin !== new URL(req.url).origin) return { res: deny("Forbidden.") };
  if (!(req.headers.get("content-type") || "").startsWith("application/json")) return { res: json(415, { error: "Send JSON." }) };
  const text = await req.text();
  if (text.length > MAX_BODY) return { res: json(413, { error: "Too large." }) };
  try { return { body: JSON.parse(text) }; } catch (_) { return { res: json(400, { error: "Bad JSON." }) }; }
}

async function api(req, env, path) {
  const { res, claims } = await access(req);
  if (res) return res;
  const email = String(claims.email || "").toLowerCase();
  if (path === "/api/responses") {
    if (req.method !== "POST") return json(405, { error: "POST only." });
    const r = await readBody(req);
    if (r.res) return r.res;
    if (!r.body || !Array.isArray(r.body.responses)) return json(400, { error: "Expected {responses: [...]}." });
    if (!env || !env.FLIGHTDECK_RESPONSES) return json(501, { error: "No FLIGHTDECK_RESPONSES binding; responses stay in this browser." });
    const at = new Date().toISOString();
    await env.FLIGHTDECK_RESPONSES.put(`responses/${email}`, JSON.stringify({ at, email, responses: r.body.responses }));
    return json(200, { ok: true, stored: r.body.responses.length, at });
  }
  // Chat Accept ingest: merge one answer into KV without wiping the page's list.
  // scripts/record_chat_accept.py writes the same shape; this route needs no bot memory.
  if (path === "/api/chat-accept") {
    if (req.method !== "POST") return json(405, { error: "POST only." });
    const r = await readBody(req);
    if (r.res) return r.res;
    const entry = r.body || {};
    const id = String(entry.id || "").trim();
    const value = String(entry.value || "accepted").trim();
    if (!id) return json(400, { error: "Expected {id, value?, comment?, timestamp?, ref?}." });
    if (!["accepted", "rejected", "comment"].includes(value)) return json(400, { error: "value must be accepted|rejected|comment." });
    if (!env || !env.FLIGHTDECK_RESPONSES) return json(501, { error: "No FLIGHTDECK_RESPONSES binding." });
    const key = `responses/${email}`;
    let raw = null;
    try { raw = JSON.parse(await env.FLIGHTDECK_RESPONSES.get(key) || "null"); } catch (_) { raw = null; }
    const at = new Date().toISOString();
    const row = {
      id,
      type: "decision",
      value,
      comment: String(entry.comment || "").slice(0, 4000),
      timestamp: String(entry.timestamp || at),
      channel: "chat",
      ref: String(entry.ref || "chat").slice(0, 200),
    };
    const prev = (raw && Array.isArray(raw.responses)) ? raw.responses : [];
    const rows = prev.filter((x) => !(x && x.id === id && (x.channel === "chat" || x.timestamp === row.timestamp)));
    rows.push(row);
    await env.FLIGHTDECK_RESPONSES.put(key, JSON.stringify({ at, email, responses: rows }));
    return json(200, { ok: true, id, stored: rows.length, at });
  }
  if (path === "/api/spark") {
    if (!env || !env.FLIGHTDECK_SPARK) return json(501, { error: "No FLIGHTDECK_SPARK binding; the page shows its rendered snapshot." });
    if (req.method === "GET") {
      const v = await env.FLIGHTDECK_SPARK.get("spark/latest");
      return v ? new Response(v, { headers: { ...HDRS, "content-type": "application/json; charset=utf-8" } }) : json(404, { error: "No reading yet." });
    }
    if (req.method !== "POST") return json(405, { error: "GET or POST only." });
    const r = await readBody(req);
    if (r.res) return r.res;
    if (!r.body || !Array.isArray(r.body.nodes)) return json(400, { error: "Expected {cluster, nodes: [...]}." });
    await env.FLIGHTDECK_SPARK.put("spark/latest", JSON.stringify(r.body));
    return json(200, { ok: true, nodes: r.body.nodes.length });
  }
  return json(404, { error: "Not found." });
}

export default {
  async fetch(req, env) {
    const path = new URL(req.url).pathname;
    return path.startsWith("/api/") ? api(req, env, path) : page.fetch(req);
  },
};
