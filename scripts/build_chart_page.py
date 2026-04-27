#!/usr/bin/env python3
"""Build the SPIVA chart page from CSV + commentary RTF."""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_explainers import rtf_to_paragraphs, render_paragraph

CHARTS_DIR = Path(__file__).resolve().parent.parent / "charts"
CSV_PATH = CHARTS_DIR / "SPIVA chart 22 yrs - Sheet1.csv"
COMMENTARY_PATH = CHARTS_DIR / "chart-text.rtf"
OUTPUT = CHARTS_DIR / "active-vs-index.html"

# --- Read data ---
rows = []
with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.reader(f)
    header = next(reader)
    for r in reader:
        if not r or not r[0].strip().isdigit():
            continue
        year = int(r[0])
        underperf = int(r[1].rstrip("%"))
        avg_perf = int(r[2].rstrip("%"))
        rows.append((year, underperf, avg_perf))

years = [r[0] for r in rows]
underperfs = [r[1] for r in rows]
avg_perfs = [r[2] for r in rows]

# --- Read commentary ---
rtf = COMMENTARY_PATH.read_text(encoding="utf-8", errors="replace")
paragraphs = rtf_to_paragraphs(rtf)
body_html = "\n".join(f"      <p>{render_paragraph(p)}</p>" for p in paragraphs)

# --- Build SVG bar chart ---
# Layout: 22 grouped years; primary blue bars for % underperformers (40-90 range),
# overlay terracotta strip for negative avg performance (-5 to +2 range).
chart_w = 920
chart_h = 380
margin_top = 30
margin_bottom = 60
margin_left = 60
margin_right = 60
plot_w = chart_w - margin_left - margin_right
plot_h = chart_h - margin_top - margin_bottom
n = len(rows)
bar_w = plot_w / n * 0.7
gap = plot_w / n * 0.3

def x_for(i):
    return margin_left + (i + 0.5) * (plot_w / n)

# Y scale for underperformers (0..100)
def y_underperf(v):
    return margin_top + plot_h * (1 - v / 100)

# Y for grid lines (left axis 0,25,50,75,100)
y_ticks_left = [0, 25, 50, 75, 100]

bars = []
for i, v in enumerate(underperfs):
    cx = x_for(i)
    x = cx - bar_w / 2
    y = y_underperf(v)
    h = (margin_top + plot_h) - y
    color = "#4A8FA8" if v < 50 else ("#C89434" if v < 70 else "#BB4F44")
    bars.append(
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{color}" rx="2"/>'
    )

# Avg performance: small dots above/below a thin baseline at y = midpoint of plot (visually offset above bars)
# We'll plot avg perf as a separate small line chart at the bottom strip below the bars.
# Use the bottom 28% of the plot area for a separate mini-chart.
mini_top = margin_top + plot_h + 8
mini_h = 0  # we'll keep it integrated; simpler: annotate above the bars

# Add x-axis labels (every 2 years)
x_labels = []
for i, y in enumerate(years):
    if y % 4 == 0 or i == 0 or i == n - 1:
        cx = x_for(i)
        x_labels.append(
            f'<text x="{cx:.1f}" y="{margin_top + plot_h + 18}" fill="#5E5A54" font-family="Inter" font-size="11" text-anchor="middle">{y}</text>'
        )

# Y-axis labels (left)
y_axis_labels = []
for v in y_ticks_left:
    yv = y_underperf(v)
    y_axis_labels.append(
        f'<text x="{margin_left - 10}" y="{yv + 4:.1f}" fill="#5E5A54" font-family="Inter" font-size="11" text-anchor="end">{v}%</text>'
    )
    y_axis_labels.append(
        f'<line x1="{margin_left}" y1="{yv:.1f}" x2="{margin_left + plot_w}" y2="{yv:.1f}" stroke="#E6DDCA" stroke-width="1" stroke-dasharray="2 4"/>'
    )

# Avg perf as small numbers above each bar
perf_labels = []
for i, v in enumerate(avg_perfs):
    cx = x_for(i)
    y = y_underperf(underperfs[i]) - 6
    color = "#4C8B5E" if v > 0 else ("#5E5A54" if v == 0 else "#BB4F44")
    sign = "+" if v > 0 else ""
    perf_labels.append(
        f'<text x="{cx:.1f}" y="{y:.1f}" fill="{color}" font-family="Inter" font-size="9.5" font-weight="600" text-anchor="middle">{sign}{v}%</text>'
    )

svg = f'''<svg viewBox="0 0 {chart_w} {chart_h}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Bar chart: percent of US large-cap active funds that underperformed the S&P 500 each year, 2004-2025">
  <rect width="{chart_w}" height="{chart_h}" fill="transparent"/>
  {''.join(y_axis_labels)}
  {''.join(bars)}
  {''.join(perf_labels)}
  <line x1="{margin_left}" y1="{margin_top + plot_h}" x2="{margin_left + plot_w}" y2="{margin_top + plot_h}" stroke="#5E5A54" stroke-width="1"/>
  {''.join(x_labels)}
  <text x="{margin_left}" y="{margin_top - 12}" fill="#1A2332" font-family="Inter" font-size="12" font-weight="600">% of US large-cap active funds underperforming the S&amp;P 500</text>
  <text x="{chart_w - margin_right}" y="{chart_h - 8}" fill="#5E5A54" font-family="Inter" font-size="10" text-anchor="end">Bars: % underperforming · Numbers above bars: avg active fund return vs S&amp;P 500</text>
</svg>'''

# --- Page template ---
HTML = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Active funds vs. the index — a 22-year scoreboard · FYFA</title>
  <meta name="description" content="The SPIVA scorecard for US large-cap active funds, 2004-2025: in most years, the majority underperform the S&P 500." />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;0,9..144,700;1,9..144,400&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg: #FCF8F1;
      --bg-alt: #F3ECDE;
      --ink: #1A2332;
      --ink-muted: #5E5A54;
      --rule: #E6DDCA;
      --accent: #B8623A;
      --accent-soft: #F2D6C3;
      --card: #FFFFFF;
      --shadow-sm: 0 1px 3px rgba(26,35,50,0.06), 0 2px 8px rgba(26,35,50,0.04);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; color: var(--ink); background: var(--bg); line-height: 1.6; font-size: 17px; -webkit-font-smoothing: antialiased; }}
    h1 {{ font-family: 'Fraunces', Georgia, serif; font-weight: 600; font-size: clamp(2.1rem, 4.5vw, 3.1rem); line-height: 1.12; letter-spacing: -0.02em; margin: 0 0 36px; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .container {{ max-width: 980px; margin: 0 auto; padding: 0 24px; }}
    .container.narrow {{ max-width: 720px; }}
    .site-nav {{ padding: 18px 0; border-bottom: 1px solid var(--rule); background: rgba(252,248,241,0.85); backdrop-filter: saturate(180%) blur(8px); position: sticky; top: 0; z-index: 50; }}
    .site-nav-inner {{ max-width: 1120px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; }}
    .site-logo {{ font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.15rem; color: var(--ink); }}
    .back-link {{ font-size: 0.92rem; color: var(--ink-muted); }}
    .back-link:hover {{ color: var(--accent); }}
    article.chartpage {{ padding: 64px 0 88px; }}
    .eyebrow {{ font-family: 'Inter', sans-serif; text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; color: var(--accent); font-weight: 600; margin-bottom: 18px; }}
    .chart-card {{ background: var(--card); border: 1px solid var(--rule); border-radius: 16px; padding: 28px 32px 36px; box-shadow: var(--shadow-sm); margin-bottom: 40px; }}
    .chart-card svg {{ width: 100%; height: auto; display: block; }}
    .chart-source {{ font-size: 0.85rem; color: var(--ink-muted); margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--rule); }}
    .legend {{ display: flex; gap: 18px; flex-wrap: wrap; margin-top: 18px; font-size: 0.85rem; color: var(--ink-muted); }}
    .legend-swatch {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 6px; vertical-align: middle; }}
    article.chartpage p {{ font-family: 'Fraunces', Georgia, serif; font-size: 1.18rem; line-height: 1.65; color: var(--ink); margin: 0 0 22px; }}
    article.chartpage p strong {{ font-weight: 600; color: var(--ink); }}
    .footer-cta {{ margin-top: 56px; padding: 28px; background: var(--card); border: 1px solid var(--rule); border-left: 4px solid var(--accent); border-radius: 12px; box-shadow: var(--shadow-sm); }}
    .footer-cta p {{ font-family: 'Inter', sans-serif !important; font-size: 0.98rem !important; line-height: 1.55 !important; margin: 0 !important; color: var(--ink-muted); }}
    .footer-cta strong {{ color: var(--ink); }}
    footer.site-footer {{ padding: 32px 0; background: var(--bg-alt); border-top: 1px solid var(--rule); font-size: 0.88rem; color: var(--ink-muted); text-align: center; }}
  </style>
</head>
<body>
  <nav class="site-nav">
    <div class="site-nav-inner">
      <a class="site-logo" href="../index.html">FYFA</a>
      <a class="back-link" href="../index.html#materials">← Back to course materials</a>
    </div>
  </nav>

  <article class="chartpage">
    <div class="container">
      <div class="eyebrow">Live chart · 2004 — 2025</div>
      <h1>Active funds vs. the index — a 22-year scoreboard</h1>

      <div class="chart-card">
        {svg}
        <div class="legend">
          <span><span class="legend-swatch" style="background:#4A8FA8"></span>Less than half underperformed</span>
          <span><span class="legend-swatch" style="background:#C89434"></span>50–70% underperformed</span>
          <span><span class="legend-swatch" style="background:#BB4F44"></span>70%+ underperformed</span>
        </div>
        <div class="chart-source">Source: S&amp;P Indices Versus Active (SPIVA) Scorecards. Numbers above each bar show the asset-weighted average return of all US domestic active equity funds minus the S&amp;P 500 return for that year. Negative values mean the average active fund lagged the index.</div>
      </div>
    </div>

    <div class="container narrow">
{body_html}
      <div class="footer-cta">
        <p>This is part of the material you'll meet across the course. The course launches <strong>May 2026</strong>. <a href="../index.html#waitlist">Join the waitlist →</a></p>
      </div>
    </div>
  </article>

  <footer class="site-footer">
    <div class="container">© 2026 FYFA · <a href="../index.html">fyfa.ca</a></div>
  </footer>
</body>
</html>
'''

OUTPUT.write_text(HTML, encoding="utf-8")
print(f"  · {OUTPUT.name} ({len(rows)} years, {len(paragraphs)} paragraphs of commentary)")
