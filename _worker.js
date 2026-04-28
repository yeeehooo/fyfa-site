/**
 * Worker entry point for fyfa-site.
 *
 * Routing model:
 *   /api/waitlist          (POST)  -> waitlist signup handler  (writes to KV)
 *   /api/waitlist-export   (GET)   -> auth-gated KV dump       (JSON or CSV)
 *   everything else                -> static assets (index.html, /data/*, /images/*, ...)
 *
 * The static-assets binding is named ASSETS in wrangler.jsonc.
 */

import { onRequestPost as handleWaitlistSubmit } from "./functions/api/waitlist.js";
import { onRequestGet as handleWaitlistExport } from "./functions/api/waitlist-export.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const handlerCtx = {
      request,
      env,
      ctx,
      waitUntil: (p) => ctx.waitUntil(p),
    };

    if (url.pathname === "/api/waitlist" && request.method === "POST") {
      return handleWaitlistSubmit(handlerCtx);
    }
    if (url.pathname === "/api/waitlist-export" && request.method === "GET") {
      return handleWaitlistExport(handlerCtx);
    }

    // Everything else: serve from static assets.
    return env.ASSETS.fetch(request);
  },
};
