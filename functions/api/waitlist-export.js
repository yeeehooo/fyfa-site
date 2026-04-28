/**
 * GET /api/waitlist-export
 *
 * Auth-gated dump of all waitlist submissions stored in KV.
 *
 * Usage:
 *   curl -H "Authorization: Bearer <ADMIN_TOKEN>" https://fyfa.ca/api/waitlist-export
 *
 * Add ?format=csv to get CSV instead of JSON.
 *
 * Bindings:
 *   - WAITLIST    (KV namespace)
 *   - ADMIN_TOKEN (secret env var) — must match the Bearer token sent
 */

export async function onRequestGet(context) {
  const { request, env } = context;

  const auth = request.headers.get("authorization") || "";
  const token = auth.replace(/^Bearer\s+/i, "").trim();
  if (!env.ADMIN_TOKEN || token !== env.ADMIN_TOKEN) {
    return new Response("Unauthorized", { status: 401 });
  }
  if (!env.WAITLIST) {
    return new Response("WAITLIST KV not bound", { status: 500 });
  }

  // Walk all keys (paginated)
  const records = [];
  let cursor;
  do {
    const page = await env.WAITLIST.list({ cursor, limit: 1000 });
    for (const k of page.keys) {
      const v = await env.WAITLIST.get(k.name);
      if (!v) continue;
      try {
        records.push(JSON.parse(v));
      } catch (_) {}
    }
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  records.sort((a, b) => (a.submitted_at || "").localeCompare(b.submitted_at || ""));

  const url = new URL(request.url);
  if (url.searchParams.get("format") === "csv") {
    const head = "submitted_at,name,email,level,country,ip\n";
    const rows = records
      .map((r) => [r.submitted_at, r.name, r.email, r.level, r.country, r.ip].map(csvCell).join(","))
      .join("\n");
    return new Response(head + rows + "\n", {
      headers: {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="fyfa-waitlist.csv"',
        "Cache-Control": "no-store",
      },
    });
  }

  return new Response(JSON.stringify({ count: records.length, records }, null, 2), {
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

function csvCell(v) {
  if (v == null) return "";
  const s = String(v);
  if (/[",\n]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
  return s;
}
