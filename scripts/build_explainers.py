#!/usr/bin/env python3
"""Convert TextEdit .rtf primers into styled HTML explainer pages."""
import re
import os
from pathlib import Path

EXPLAINERS_DIR = Path(__file__).resolve().parent.parent / "explainers"

# Map slugs → (display title, cluster label)
META = {
    "loss-aversion":        ("Loss aversion",        "Behavioral biases"),
    "confirmation-bias":    ("Confirmation bias",    "Behavioral biases"),
    "herd-mentality":       ("Herd mentality",       "Behavioral biases"),
    "endowment-bias":       ("Endowment bias",       "Behavioral biases"),
    "roic":                 ("ROIC",                 "Investment concepts"),
    "free-cash-flow":       ("Free cash flow",       "Investment concepts"),
    "shareholder-returns":  ("Shareholder returns",  "Investment concepts"),
    "economic-moat":        ("Economic moat",        "Investment concepts"),
}


def rtf_to_paragraphs(rtf_text):
    """Tiny RTF parser tuned for TextEdit output.
    Returns list of paragraphs, each as list of (text, bold) runs."""
    # Drop the font/color/style/info groups entirely.
    for table in ("fonttbl", "colortbl", "expandedcolortbl", "stylesheet", "info"):
        rtf_text = re.sub(r"\{\\\*?\\?" + table + r"[^{}]*\}", "", rtf_text, flags=re.DOTALL)

    paragraphs = [[]]
    bold = False
    i = 0
    n = len(rtf_text)
    current_text = []

    def flush_run():
        if current_text:
            paragraphs[-1].append(("".join(current_text), bold))
            current_text.clear()

    while i < n:
        c = rtf_text[i]
        if c == "\\":
            # Control word or escaped character
            j = i + 1
            if j >= n:
                break
            nx = rtf_text[j]
            if nx in "\\{}":
                current_text.append(nx)
                i = j + 1
                continue
            if nx == "'":
                # \'XX  → byte
                hexstr = rtf_text[j+1:j+3]
                try:
                    byte = bytes([int(hexstr, 16)])
                    current_text.append(byte.decode("cp1252", errors="replace"))
                except ValueError:
                    pass
                i = j + 3
                continue
            if nx == "\n" or nx == "\r":
                # line continuation = paragraph break (TextEdit uses bare \ at end of line)
                flush_run()
                if paragraphs[-1]:
                    paragraphs.append([])
                i = j + 1
                continue
            if nx == "*":
                # \* introduces an ignorable destination — skip the next group
                i = j + 1
                continue
            if nx.isalpha():
                # control word
                m = re.match(r"([a-zA-Z]+)(-?\d+)?\s?", rtf_text[j:])
                if m:
                    word = m.group(1)
                    arg = m.group(2)
                    i = j + m.end()
                    if word == "par":
                        flush_run()
                        if paragraphs[-1]:
                            paragraphs.append([])
                    elif word == "b":
                        flush_run()
                        bold = (arg != "0")
                    elif word == "u" and arg:
                        # \uXXXX unicode codepoint, followed by a fallback char to skip
                        try:
                            cp = int(arg)
                            if cp < 0:
                                cp += 65536
                            current_text.append(chr(cp))
                        except ValueError:
                            pass
                        # skip the next single character (the fallback)
                        if i < n and rtf_text[i] not in (" ", "\n", "\r"):
                            i += 1
                    # other control words are ignored
                    continue
                else:
                    i = j + 1
                    continue
            # Unknown escape, skip
            i = j + 1
            continue
        if c == "{":
            # group start — track but don't break runs
            i += 1
            continue
        if c == "}":
            i += 1
            continue
        if c in ("\n", "\r"):
            i += 1
            continue
        current_text.append(c)
        i += 1

    flush_run()
    return [p for p in paragraphs if p]


def clean_text(t):
    """Strip LaTeX-style math fences and percent escapes the LLM may have emitted."""
    # $90\%$ → 90%, $90%$ → 90%, $90$ → 90
    t = re.sub(r"\$(\d[\d,.]*)\\?%\$", r"\1%", t)
    t = re.sub(r"\$(\d[\d,.]*)\$", r"\1", t)
    # Stray \% outside math fences
    t = t.replace(r"\%", "%")
    return t


def render_paragraph(runs):
    """Convert list of (text, bold) into HTML paragraph content."""
    out = []
    for text, bold in runs:
        text = clean_text(text)
        # escape minimal HTML
        t = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if bold and t.strip():
            out.append(f"<strong>{t}</strong>")
        else:
            out.append(t)
    return "".join(out).strip()


# Match a formula paragraph: a CamelCase or short term + " = " + expression.
# Examples: "ROIC = NOPAT / Invested Capital",
#           "FCF = Operating Cash Flow - Capital Expenditures",
#           "Shareholder Yield = (Dividends + Buybacks) / Market Cap"
FORMULA_RE = re.compile(r"^([A-Z][A-Za-z ]{1,40})\s*=\s*(.+)$")


def _strip_outer_parens(s):
    s = s.strip()
    if s.startswith("(") and s.endswith(")"):
        # Only strip if these parens wrap the whole expression
        depth = 0
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i < len(s) - 1:
                    return s
        return s[1:-1].strip()
    return s


def _render_expression(expr):
    """Render the right-hand side of a formula. If it contains a top-level
    ' / ' division, render as a stacked fraction; otherwise return as text."""
    # Find top-level " / "
    depth = 0
    for i in range(len(expr) - 2):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr[i:i+3] == " / ":
            num = _strip_outer_parens(expr[:i])
            den = _strip_outer_parens(expr[i+3:])
            return (
                f'<span class="frac">'
                f'<span class="frac-num">{num}</span>'
                f'<span class="frac-den">{den}</span>'
                f'</span>'
            )
    return expr


def render_block(runs):
    """Render a paragraph; if it's a formula line, wrap as a formula box."""
    inner = render_paragraph(runs)
    # Strip simple wrapping <strong> tags to test the underlying text shape.
    bare = re.sub(r"</?strong>", "", inner)
    m = FORMULA_RE.match(bare.strip())
    if not m:
        return f"      <p>{inner}</p>"
    label, expr = m.group(1).strip(), m.group(2).strip()
    rhs_html = _render_expression(expr)
    return (
        f'      <div class="formula">'
        f'<span class="formula-label">{label}</span>'
        f'<span class="formula-eq">=</span>'
        f'<span class="formula-rhs">{rhs_html}</span>'
        f'</div>'
    )


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — FYFA explainer</title>
  <meta name="description" content="{summary}" />
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
    .container {{ max-width: 720px; margin: 0 auto; padding: 0 24px; }}
    .site-nav {{ padding: 18px 0; border-bottom: 1px solid var(--rule); background: rgba(252,248,241,0.85); backdrop-filter: saturate(180%) blur(8px); position: sticky; top: 0; z-index: 50; }}
    .site-nav-inner {{ max-width: 1120px; margin: 0 auto; padding: 0 24px; display: flex; align-items: center; justify-content: space-between; }}
    .site-logo {{ font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.15rem; color: var(--ink); }}
    .back-link {{ font-size: 0.92rem; color: var(--ink-muted); }}
    .back-link:hover {{ color: var(--accent); }}
    article.explainer {{ padding: 64px 0 88px; }}
    .eyebrow {{ font-family: 'Inter', sans-serif; text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; color: var(--accent); font-weight: 600; margin-bottom: 18px; }}
    article.explainer p {{ font-family: 'Fraunces', Georgia, serif; font-size: 1.18rem; line-height: 1.65; color: var(--ink); margin: 0 0 22px; }}
    article.explainer p:first-of-type {{ font-size: 1.28rem; line-height: 1.55; }}
    article.explainer p strong {{ font-weight: 600; color: var(--ink); }}
    .formula {{
      display: flex; align-items: center; justify-content: center; gap: 14px;
      flex-wrap: wrap;
      margin: 18px 0 30px;
      padding: 22px 28px;
      background: var(--accent-soft);
      border: 1px solid #EBC6AE;
      border-radius: 12px;
      font-family: 'Fraunces', Georgia, serif;
      font-size: 1.16rem;
      color: #6B3520;
      line-height: 1.4;
    }}
    .formula .formula-label {{ font-weight: 600; }}
    .formula .formula-eq {{ font-style: italic; opacity: 0.7; font-size: 1.25rem; }}
    .formula .formula-rhs {{ display: inline-flex; align-items: center; }}
    .formula .frac {{
      display: inline-flex; flex-direction: column; align-items: center;
      vertical-align: middle; line-height: 1.25;
    }}
    .formula .frac-num {{ padding: 0 10px 6px; }}
    .formula .frac-den {{ padding: 6px 10px 0; border-top: 1.5px solid #B8623A; }}
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

  <article class="explainer">
    <div class="container">
      <div class="eyebrow">Explainer · {cluster}</div>
      <h1>{title}</h1>
{body}
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
"""


def build():
    for slug, (title, cluster) in META.items():
        src = EXPLAINERS_DIR / f"{slug}.rtf"
        if not src.exists():
            print(f"  · MISSING: {src.name}")
            continue
        rtf = src.read_text(encoding="utf-8", errors="replace")
        paragraphs = rtf_to_paragraphs(rtf)
        body_html = "\n".join(render_block(p) for p in paragraphs)
        # Generate a meta description from the first paragraph's plain text
        first_text = "".join(t for t, _ in paragraphs[0]) if paragraphs else ""
        summary = re.sub(r'\s+', ' ', first_text).strip()[:155]
        summary = summary.replace('"', '&quot;')
        out = HTML_TEMPLATE.format(title=title, cluster=cluster, body=body_html, summary=summary)
        dest = EXPLAINERS_DIR / f"{slug}.html"
        dest.write_text(out, encoding="utf-8")
        print(f"  · {slug}.html ({len(paragraphs)} paragraphs)")


if __name__ == "__main__":
    build()
