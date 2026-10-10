#!/usr/bin/env python3
"""Render findings JSON to a self-contained HTML report. Stdlib only.

Usage: render_report.py findings.json [--title T] [--out review.html]
"""
import html
import json
import sys
from collections import Counter

SEV = ["Critical", "High", "Medium", "Low", "Info"]
PILLARS = ["Security", "Reliability", "Operational Excellence", "Performance Efficiency", "Cost Optimization", "Sustainability"]
WEIGHT = {"Critical": 10, "High": 6, "Medium": 3, "Low": 1, "Info": 0}


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    data = json.load(open(sys.argv[1]))
    title = arg("--title", "Architecture Review")
    out = arg("--out", "review.html")
    fs = data["findings"]
    e = html.escape
    sev_counts = Counter(f["severity"] for f in fs)
    pillar_score = {}
    for p in PILLARS:
        penalty = sum(WEIGHT[f["severity"]] for f in fs if f["pillar"] == p)
        pillar_score[p] = max(0, 100 - penalty * 4)

    bars = "".join(
        f'<div class="row"><span>{e(p)}</span><div class="bar"><i style="width:{s}%" class="{"g" if s >= 80 else "y" if s >= 55 else "r"}"></i></div><b>{s}</b></div>'
        for p, s in pillar_score.items())
    chips = "".join(f'<span class="chip {s.lower()}">{s} {sev_counts.get(s, 0)}</span>' for s in SEV)
    cards = []
    for f in sorted(fs, key=lambda f: SEV.index(f["severity"])):
        loc = f'{e(f.get("file", ""))}:{f.get("line", "")}' if f.get("file") else "review finding"
        cards.append(f'''<details class="card {f["severity"].lower()}"><summary><span class="tag">{e(f["severity"])}</span>
<b>{e(f["title"])}</b><em>{e(f["pillar"])} / {e(f["id"])}</em></summary>
<p><strong>Where:</strong> {loc} {('(' + e(f["resource"]) + ')') if f.get("resource") else ""}</p>
{('<pre>' + e(f["evidence"]) + '</pre>') if f.get("evidence") else ""}
<p><strong>Fix:</strong> {e(f.get("remediation", ""))}</p>
<p class="src">Source: {e(f.get("source", "scanner"))}</p></details>''')
    inv = "".join(f"<tr><td>{e(k)}</td><td>{v}</td></tr>" for k, v in data.get("inventory", {}).items())

    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>
:root{{--bg:#fff;--fg:#1a1d21;--mut:#5f6b7a;--card:#f5f7fa;--bd:#dde2e8;--r:#c62828;--o:#e65100;--y:#b58900;--b:#1565c0;--g:#2e7d32}}
@media(prefers-color-scheme:dark){{:root{{--bg:#12151a;--fg:#e8ecf1;--mut:#9aa7b5;--card:#1b2028;--bd:#2c3440;--r:#ef5350;--o:#ff9800;--y:#e0b400;--b:#64b5f6;--g:#66bb6a}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:880px;margin:0 auto;padding:24px 16px}}h1{{margin:0 0 4px}}h2{{margin-top:32px}}
.chip{{display:inline-block;padding:2px 10px;border-radius:12px;margin:0 6px 6px 0;font-weight:600;font-size:13px;border:1px solid var(--bd)}}
.critical{{--c:var(--r)}}.high{{--c:var(--o)}}.medium{{--c:var(--y)}}.low{{--c:var(--b)}}.info{{--c:var(--mut)}}
.chip{{color:var(--c)}}.row{{display:grid;grid-template-columns:190px 1fr 36px;gap:10px;align-items:center;margin:6px 0}}
.bar{{background:var(--card);border:1px solid var(--bd);height:12px;border-radius:6px;overflow:hidden}}.bar i{{display:block;height:100%}}
.g{{background:var(--g)}}.y{{background:var(--y)}}.r{{background:var(--r)}}
.card{{background:var(--card);border:1px solid var(--bd);border-left:4px solid var(--c);border-radius:6px;margin:8px 0;padding:8px 12px}}
summary{{cursor:pointer;display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}}summary em{{color:var(--mut);font-size:13px;margin-left:auto}}
.tag{{color:var(--c);font-weight:700;font-size:12px;text-transform:uppercase}}pre{{overflow-x:auto;background:var(--bg);padding:8px;border-radius:4px;border:1px solid var(--bd)}}
.src{{color:var(--mut);font-size:12px}}table{{border-collapse:collapse}}td{{padding:2px 14px 2px 0}}
@media(max-width:560px){{.row{{grid-template-columns:120px 1fr 30px}}}}
</style><main><h1>{e(title)}</h1><p style="color:var(--mut)">{len(fs)} findings. Scanner results are heuristic; High and Critical items should be confirmed in code.</p>
<div>{chips}</div><h2>Pillar health</h2>{bars}<h2>Findings</h2>{"".join(cards) or "<p>No findings.</p>"}
<h2>Resource inventory</h2><table>{inv}</table></main></html>'''
    open(out, "w").write(page)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
