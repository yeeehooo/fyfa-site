# Cloudflare setup — barometer + waitlist + email

One-time wiring inside the Cloudflare dashboard. After this is done the site
is fully self-driving: weekly cron updates the barometer, the waitlist form
captures signups, and emails to askme@fyfa.ca land in your inbox.

## 1. Bind a KV namespace for the waitlist

The waitlist form posts to `/api/waitlist` (a Pages Function). Submissions
are stored in a Workers KV namespace bound to the Pages project.

1. **Create the namespace.**
   Cloudflare dashboard → **Workers & Pages → KV → Create namespace**
   - Name: `fyfa-waitlist` (any name works)

2. **Bind it to the Pages project.**
   Workers & Pages → **fyfa-site → Settings → Bindings → Add binding**
   - Type: `KV namespace`
   - Variable name: `WAITLIST` *(must match exactly — the function reads `env.WAITLIST`)*
   - KV namespace: `fyfa-waitlist`

3. **Add an admin token** so you can read out signups via `/api/waitlist-export`.
   Same Bindings page → **Add variable and secret** (Plaintext is fine):
   - Variable name: `ADMIN_TOKEN`
   - Value: any long random string (e.g. paste from `openssl rand -hex 32`)

4. **(Optional) Email notifications via Resend.**
   If you want each signup to ping your inbox, sign up at [resend.com](https://resend.com)
   (free 100 emails/day), verify the `fyfa.ca` domain, and add:
   - `RESEND_API_KEY` (Secret) — your Resend API key
   - `NOTIFY_EMAIL` (Plaintext) — `askme@fyfa.ca`
   - `NOTIFY_FROM` (Plaintext, optional) — `FYFA waitlist <waitlist@fyfa.ca>` *(must be on the verified domain)*

   If you skip this, signups still get stored in KV — you just have to pull them yourself.

5. **Re-deploy** the Pages project (any push to main, or **Deployments → Retry**).

### Reading the signups

Once a few are in:

```bash
# JSON
curl -H "Authorization: Bearer $ADMIN_TOKEN" https://fyfa.ca/api/waitlist-export

# CSV (downloads file)
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     -o waitlist.csv \
     'https://fyfa.ca/api/waitlist-export?format=csv'
```

## 2. Cloudflare Email Routing for askme@fyfa.ca

Replaces the Porkbun forwarding rules.

1. **Open the routing UI.** Cloudflare dashboard → select `fyfa.ca` → **Email → Email Routing → Get started**.

2. **Add a destination address.**
   - Click **Destination addresses → Add destination**
   - Enter your real personal Gmail (the one you want forwards to land in)
   - Cloudflare emails you a verification link — click it.

3. **Add the route.**
   - Custom address: `askme@fyfa.ca`
   - Action: `Send to an email`
   - Destination: your verified Gmail
   - Save.

4. **Optional aliases worth adding while you're there:**
   - `waitlist@fyfa.ca` → same Gmail (used as the "from" for notification emails)
   - `hello@fyfa.ca` → same Gmail (sometimes people guess this)

5. **Replace the DNS records.**
   Email Routing tab → **Settings → DNS records → Add records automatically**.
   This will:
   - Add Cloudflare's MX records (3 of them: `*.mx.cloudflare.net`)
   - Add a Cloudflare-issued SPF record
   - You'll be prompted to **delete** the old Porkbun MX records and the old SPF TXT.

6. **Verify.** Send yourself a test from another address to `askme@fyfa.ca`. Should land in Gmail within ~30 seconds.

## 3. Trigger the first barometer build

GitHub → fyfa-site repo → **Actions → Update market barometer → Run workflow**.

It runs in ~60 seconds, commits `data/barometer.json` and `data/history/*.csv`, Cloudflare auto-deploys, and the gauge hydrates with real numbers.

After that it runs automatically every Monday at 14:00 UTC.

## Troubleshooting

**Form returns "Network error" or 500:**
Check the Pages project → Functions logs (Workers & Pages → fyfa-site → Functions). The most common cause is the `WAITLIST` KV binding name mismatched.

**Barometer shows "—" for every indicator:**
The first GHA run hasn't happened yet. Trigger it manually as described above.

**Resend emails not arriving:**
- Verify the domain in Resend (DKIM + SPF records added to Cloudflare DNS).
- Check Resend's logs for delivery status.
- The function logs the full Resend response on failure — check Pages Functions logs.

**Email Routing not delivering:**
- Verify the destination address (the click-the-link step is required).
- Check that old Porkbun MX records are fully removed — both ends will conflict.
