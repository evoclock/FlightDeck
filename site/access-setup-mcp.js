async () => {
  // One-time Cloudflare Access setup for a FlightDeck hostname.
  // Replace every placeholder before running. Do not commit real account ids or emails.
  // Run via the Cloudflare MCP execute tool with code="$file:site/access-setup-mcp.js".
  // Idempotent. Needs scopes: access-acct.write, access.write. Access must be enabled on the account.
  const A = "ACCOUNT_ID";
  const HOST = "example.workers.dev";
  const EMAIL = "you@example.com";
  const TEAM = "TEAM.cloudflareaccess.com";
  if (A === "ACCOUNT_ID" || EMAIL === "you@example.com" || HOST === "example.workers.dev" || TEAM.startsWith("TEAM.")) {
    return { error: "Replace the placeholders in site/access-setup-mcp.js before running. Do not commit the filled file." };
  }
  const R = (method, path, body) => cloudflare.request({ method, path: `/accounts/${A}${path}`, body });
  let org; try { org = (await R("GET", "/access/organizations")).result; } catch (e) { org = null; }
  if (!org || !org.auth_domain) org = (await R("POST", "/access/organizations", { name: "FlightDeck", auth_domain: TEAM })).result;
  const idps = (await R("GET", "/access/identity_providers")).result || [];
  let otp = idps.find((i) => i.type === "onetimepin");
  if (!otp) otp = (await R("POST", "/access/identity_providers", { name: "One-time PIN", type: "onetimepin", config: {} })).result;
  const pols = (await R("GET", "/access/policies")).result || [];
  let pol = pols.find((p) => p.name === "flightdeck-demo: allow email");
  if (!pol) pol = (await R("POST", "/access/policies", { name: "flightdeck-demo: allow email", decision: "allow", include: [{ email: { email: EMAIL } }], session_duration: "24h" })).result;
  const apps = (await R("GET", "/access/apps")).result || [];
  let app = apps.find((a) => a.domain === HOST);
  const appBody = { name: "FlightDeck", domain: HOST, type: "self_hosted", session_duration: "24h",
    allowed_idps: [otp.id], auto_redirect_to_identity: true, app_launcher_visible: false,
    policies: [{ id: pol.id, precedence: 1 }] };
  app = app ? (await R("PUT", `/access/apps/${app.id}`, appBody)).result : (await R("POST", "/access/apps", appBody)).result;
  return { team_domain: org.auth_domain, app_id: app.id, app_name: app.name, aud: app.aud, policy_id: pol.id, otp_idp: otp.id };
}
