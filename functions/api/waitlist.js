/**
 * POST /api/waitlist
 *
 * Receives waitlist signup submissions, validates, stores in Workers KV,
 * and (optionally) sends a notification email via Resend.
 *
 * Cloudflare Pages bindings expected (set in dashboard):
 *   - WAITLIST       (KV namespace binding)        — required for storage
 *   - RESEND_API_KEY (env var)                     — optional; notification email
 *   - NOTIFY_EMAIL   (env var, e.g. askme@fyfa.ca) — required if RESEND_API_KEY set
 *
 * The function gracefully degrades: if KV is unbound, we still return success
 * to the user but log a warning. If Resend is not configured, we just skip the
 * email step.
 */

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const MAX_LEN = 200;

export async function onRequestPost(context) {
  const { request, env } = context;

  // Parse body — accept JSON or form-encoded
  let body = {};
  try {
    const ct = request.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      body = await request.json();
    } else {
      const fd = await request.formData();
      body = Object.fromEntries(fd);
    }
  } catch (_) {
    return json({ ok: false, error: "Could not read your submission." }, 400);
  }

  // Honeypot — bots tend to fill every input. Silently accept.
  if ((body.website || "").toString().trim() !== "") {
    return json({ ok: true });
  }

  const name = (body.name || "").toString().trim();
  const email = (body.email || "").toString().trim().toLowerCase();
  const level = (body.level || "").toString().trim();

  if (!name) return json({ ok: false, error: "Please enter your name." }, 400);
  if (!EMAIL_RE.test(email)) return json({ ok: false, error: "Please enter a valid email address." }, 400);
  if (name.length > MAX_LEN || email.length > MAX_LEN || level.length > MAX_LEN) {
    return json({ ok: false, error: "Input too long." }, 400);
  }

  const now = new Date().toISOString();
  const record = {
    name,
    email,
    level,
    submitted_at: now,
    ip: request.headers.get("cf-connecting-ip") || "",
    user_agent: request.headers.get("user-agent") || "",
    country: (request.cf && request.cf.country) || "",
  };

  // Store in KV if the binding exists. Key is "<iso>__<email>" so it's
  // both unique and chronologically sortable.
  if (env.WAITLIST) {
    try {
      const key = `${now}__${email}`;
      await env.WAITLIST.put(key, JSON.stringify(record));
    } catch (e) {
      console.error("KV put failed:", e && e.message);
    }
  } else {
    console.warn("WAITLIST KV binding not set — submission not stored");
  }

  // Optional notification email via Resend.
  if (env.RESEND_API_KEY && env.NOTIFY_EMAIL) {
    try {
      const r = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${env.RESEND_API_KEY}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          from: env.NOTIFY_FROM || "FYFA waitlist <waitlist@fyfa.ca>",
          to: env.NOTIFY_EMAIL,
          reply_to: email,
          subject: `New FYFA waitlist signup: ${name}`,
          text:
            `Name:    ${name}\n` +
            `Email:   ${email}\n` +
            `Level:   ${level || "—"}\n` +
            `When:    ${now}\n` +
            `Country: ${record.country || "—"}\n`,
        }),
      });
      if (!r.ok) console.error("Resend send failed:", r.status, await r.text());
    } catch (e) {
      console.error("Resend send error:", e && e.message);
    }
  }

  return json({ ok: true });
}

// Block other methods cleanly
export const onRequestGet = () =>
  json({ ok: false, error: "Method not allowed." }, 405);

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}
