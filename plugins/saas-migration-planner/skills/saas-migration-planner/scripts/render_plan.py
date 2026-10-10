#!/usr/bin/env python3
"""Render plan.json to a self-contained HTML roadmap. Stdlib only.

Usage: render_plan.py plan.json [--title T] [--out plan.html]
"""
import html
import json
import sys
from datetime import date, datetime

e = html.escape


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def ul(items):
    return "<ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    p = json.load(open(sys.argv[1]))
    title = arg("--title", f"{p['title']}: {p['source'].title()} to {p['target'].title()}")
    out = arg("--out", "plan.html")
    waves, items = p["waves"], p["items"]

    # timeline
    t0 = min(d(w["start"]) for w in waves)
    t1 = max(d(w["end"]) for w in waves)
    span = max(1, (t1 - t0).days)
    rows = []
    for fz in p["settings"]["freezes"]:
        a, b = (d(x) for x in fz.split(":"))
        rows.append(f'<div class="freeze" style="left:{100*(a-t0).days/span:.1f}%;width:{max(1,100*(b-a).days/span):.1f}%" title="Freeze {fz}"></div>')
    lanes = ""
    for w in waves:
        left = 100 * (d(w["start"]) - t0).days / span
        width = max(2, 100 * ((d(w["end"]) - d(w["start"])).days + 1) / span)
        tag = " (held for calendar anchor)" if w.get("shifted_for_anchor") else " (after freeze)" if w["shifted_for_freeze"] else ""
        lanes += (f'<div class="lane"><span class="ln">{e(w["label"])}</span><div class="track">'
                  f'<div class="wv" style="left:{left:.1f}%;width:{width:.1f}%">{len(w["items"])} items</div></div></div>'
                  f'<div class="cap">{e(w["start"])} to {e(w["end"])}, cutover {e(w["cutover"])}, hypercare to {e(w["hypercare_until"])}{e(tag)}</div>')
    timeline = f'<div class="tl">{"".join(rows)}{lanes}</div>'

    t = p["totals"]["by_level"]
    cards = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for k, v in [
        ("items", p["totals"]["items"]), ("waves", len(waves)), ("effort-days", p["totals"]["effort_days"]),
        ("high or critical", t.get("High", 0) + t.get("Critical", 0)), ("need a decision", len(p["needs_decision"]))])

    dec = ""
    if p["needs_decision"]:
        dec = "<h2>Needs a decision before it can be scheduled</h2>" + "".join(
            f'<div class="alert"><b>{e(n["name"])}</b> (risk {n["risk"]}, {n["users"]:,} users)<br>{e(n["why"])}</div>' for n in p["needs_decision"])
    if p["cycles"]:
        dec += f'<div class="alert"><b>Dependency cycle</b> among {e(", ".join(p["cycles"]))}. Review and break the loop.</div>'
    if p["inventory_errors"]:
        dec += "<div class='alert'><b>Inventory problems</b>" + ul(p["inventory_errors"]) + "</div>"

    wave_html = ""
    byname = {i["name"]: i for i in items}
    for w in waves:
        trs = ""
        for n in w["items"]:
            i = byname[n]
            trs += (f'<tr><td><details><summary>{e(i["name"])}</summary>{ul(i["checks"])}'
                    f'<p class="mut">Owner: {e(i["owner"] or "unassigned")}. {e(i["notes"])}</p></details></td>'
                    f'<td>{e(i["type_label"])}</td><td><div class="rb {i["level"].lower()}"><i style="width:{i["risk"]}%"></i></div>{i["risk"]} {e(i["level"])}</td>'
                    f'<td>{e("; ".join(i["drivers"]))}</td><td>{i["effort_days"]}d</td></tr>')
        gating = f'<p><b>Gating:</b></p>{ul(w["gating"])}' if w["gating"] else ""
        comms = "".join(f'<tr><td>{e(c["when"])}</td><td>{e(c["what"])}</td></tr>' for c in w["comms"])
        wave_html += (f'<section class="wave"><h3>{e(w["label"])} <small>cutover {e(w["cutover"])}</small></h3>'
                      f'<table><tr><th>Item</th><th>Type</th><th>Risk</th><th>Drivers</th><th>Effort</th></tr>{trs}</table>{gating}'
                      f'<details><summary>Communications calendar</summary><table>{comms}</table></details></section>')

    gcards = "".join(f'<div class="g {g["severity"].lower()}"><b>{e(g["severity"])}</b> {e(g["title"])}<p>{e(g["detail"])}</p></div>' for g in p["gotchas"])
    phases = "".join(f'<div class="ph"><b>{k}. {e(ph["name"])}</b>{ul(ph["activities"])}</div>' for k, ph in enumerate(p["phases"], 1))
    decisions = "".join(f'<li><b>{e(x["title"])}</b>: {e(" / ".join(x["options"]))}</li>' for x in p["decisions"])

    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>
:root{{--bg:#fff;--fg:#1a1d21;--mut:#5f6b7a;--card:#f5f7fa;--bd:#dde2e8;--r:#c62828;--o:#e65100;--y:#b58900;--b:#1565c0;--g:#2e7d32;--ac:#3949ab}}
@media(prefers-color-scheme:dark){{:root{{--bg:#12151a;--fg:#e8ecf1;--mut:#9aa7b5;--card:#1b2028;--bd:#2c3440;--r:#ef5350;--o:#ff9800;--y:#e0b400;--b:#64b5f6;--g:#66bb6a;--ac:#8c9eff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}main{{max-width:960px;margin:0 auto;padding:24px 16px}}
h1{{margin:0}}h2{{margin-top:36px;border-bottom:1px solid var(--bd);padding-bottom:4px}}.mut,small{{color:var(--mut)}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}}.stat{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:10px 16px;min-width:90px}}
.stat b{{display:block;font-size:24px}}.stat span{{color:var(--mut);font-size:12px}}
.tl{{position:relative;margin-top:12px}}.freeze{{position:absolute;top:0;bottom:0;background:repeating-linear-gradient(45deg,transparent 0 6px,var(--bd) 6px 8px);opacity:.7;margin-left:90px;max-width:calc(100% - 90px)}}
.lane{{display:flex;align-items:center;gap:8px;margin-top:8px;position:relative}}.ln{{width:82px;font-weight:600;font-size:13px}}
.track{{flex:1;height:26px;background:var(--card);border:1px solid var(--bd);border-radius:4px;position:relative}}
.wv{{position:absolute;top:2px;bottom:2px;background:var(--ac);color:#fff;border-radius:3px;font-size:12px;text-align:center;line-height:20px;overflow:hidden}}
.cap{{margin-left:90px;color:var(--mut);font-size:12px}}
table{{width:100%;border-collapse:collapse;margin:8px 0}}th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);vertical-align:top;font-size:13px}}
.wave{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:8px 14px;margin:14px 0}}.wave h3{{margin:6px 0}}
.rb{{width:70px;height:8px;background:var(--bd);border-radius:4px;overflow:hidden;margin-bottom:2px}}.rb i{{display:block;height:100%}}
.rb.low i{{background:var(--g)}}.rb.medium i{{background:var(--y)}}.rb.high i{{background:var(--o)}}.rb.critical i{{background:var(--r)}}
.alert{{border-left:4px solid var(--r);background:var(--card);padding:8px 12px;margin:8px 0;border-radius:4px}}
.g{{border-left:4px solid var(--b);background:var(--card);padding:8px 12px;margin:8px 0;border-radius:4px}}.g p{{margin:4px 0 0;color:var(--mut)}}
.g.critical{{border-color:var(--r)}}.g.high{{border-color:var(--o)}}.g.medium{{border-color:var(--y)}}
.phs{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px}}.ph{{background:var(--card);border:1px solid var(--bd);border-radius:8px;padding:8px 12px}}
ul{{margin:4px 0;padding-left:20px}}summary{{cursor:pointer}}
@media(max-width:640px){{th:nth-child(4),td:nth-child(4){{display:none}}.cap{{margin-left:0}}.ln{{width:60px}}.freeze{{margin-left:68px}}}}
</style><main>
<h1>{e(title)}</h1><p class="mut">{e(p["summary"])}<br>Generated {e(p["generated"])}. Scores are decision aids; confirm Critical and High items with owners and vendors.</p>
<div class="stats">{cards}</div>{dec}
<h2>Roadmap</h2>{timeline}
<h2>Waves</h2>{wave_html}
<h2>Known gotchas for this migration</h2>{gcards}
<h2>Decisions to record (ADRs)</h2><ul>{decisions}</ul>
<h2>Phases</h2><div class="phs">{phases}</div>
<h2>Cutover day checklist</h2>{ul(p["cutover_checklist"])}
<h2>Rollback</h2>{ul(p["rollback"])}
<h2>Exit criteria</h2>{ul(p["exit_criteria"])}
<h2>Stakeholders</h2>{ul(p["stakeholders"])}
<h2>How to build the inventory</h2>{ul(p["discovery"])}
</main></html>'''
    open(out, "w").write(page)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
