# fyfa-site

Source for [fyfa.ca](https://fyfa.ca) — the companion site for Yee's AI-assisted investing course.

## Quick look

Open `index.html` in a browser to see the current prototype. Everything is a single file of HTML + inline CSS + a bit of SVG for the gauge — no build step required to preview.

## What lives where

```
fyfa-site/
├── index.html              # The site (single-file prototype)
├── images/
│   ├── headshot.png        # <-- DROP YOUR GHIBLI PORTRAIT HERE (see note below)
│   ├── ai-guide.jpg        # Extracted from course PDF
│   ├── barometer-illustration.jpg
│   ├── panic-trader.jpg
│   └── pdf-extracts/       # Other images extracted from the PDF
├── data/
│   ├── aaii-history.csv    # 240 months of AAII retail cash levels, seeded
│   ├── articles.json       # (to be written by weekly job)
│   └── barometer.json      # (to be written by weekly job)
├── scripts/                # (to be populated with data-refresh Python scripts)
├── course-materials/       # (drop downloadable PDFs/charts here as they're ready)
└── .github/workflows/      # (to be populated with GitHub Actions cron)
```

## What you need to do next

1. **Drop your headshot into `/images/headshot.png`.** The Ghibli cartoon portrait you sent me earlier — export it from wherever you have it saved and drop it in. The site falls back to a placeholder graphic if it's missing, so this is cosmetic but obvious.
2. **Review the prototype** and send feedback — anything on copy, layout, colors, wordmark, sections, ordering, the barometer design.
3. **Once Cloudflare finishes propagating from Porkbun**, we'll connect a GitHub repo to Cloudflare Pages and this folder becomes the deploy source.

## Still stubbed

- All article return percentages are placeholders. The weekly Python job will replace them with live yfinance data.
- All barometer sub-scores are placeholders except AAII (the CSV is seeded and ready).
- The waitlist form is not wired to anywhere yet (Formspree or similar goes in at deploy time).
- No analytics, no contact-form backend yet.

## Design intent

Warm cream background, deep navy text, terracotta accent, muted teal secondary. Fraunces serif for headings (has a slight hand-drawn warmth that echoes the Ghibli aesthetic), Inter for body. Rounded corners, generous spacing, professional but not stiff.
