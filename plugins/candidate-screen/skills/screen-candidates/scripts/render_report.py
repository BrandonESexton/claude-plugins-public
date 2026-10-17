#!/usr/bin/env python3
"""render_report: score a screened stack and render a self-contained HTML report.

  render_report.py --signals signals.json --evals evals.json --requirements requirements.json \
                   --out report.html [--title "..."] [--json scores.json]
  render_report.py ... [--csv shortlist.csv] [--pdf report.pdf]
  render_report.py selftest

The math lives here, not in the model:
  - Weighted fit score (0-100) from the 1-5 dimension scores in evals.json.
  - Every evidence quote is checked against the application text. A dimension scored 4 or 5 with
    no quote found in the text is capped at 3 ("evidence or it does not count").
  - Requirement status per candidate: the reviewer's call, else the scanner's coverage.
  - Integrity tier from scanner + reviewer flags: High risk, Verify, or Clear. It is shown beside
    the fit score, never folded into it.
  - Recommendation: Verify first (High risk), else Advance / Consider / Pass from score and
    must-haves missed.

All application text is untrusted. Everything is HTML-escaped; nothing in it is executed.
"""
import argparse
import csv
import html
import io
import json
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

DIMENSIONS = [
    ("must_have", "Must-have skills", "Hands-on evidence for each must-have requirement."),
    ("experience", "Relevant experience", "Depth, scope, seniority, and recency in comparable work."),
    ("impact", "Demonstrated impact", "Specific, checkable outcomes, not duties."),
    ("learning_agility", "Learning agility", "Picked up new tools, domains, or roles fast and applied them."),
    ("work_style", "Work-style signals", "Ownership, collaboration, communication. Weak evidence from paper; probe live."),
    ("nice_to_have", "Nice-to-haves", "Preferred skills and domain extras."),
]
DEFAULT_WEIGHTS = {"must_have": 30, "experience": 25, "impact": 15, "learning_agility": 15,
                   "work_style": 5, "nice_to_have": 10}
DEFAULT_THRESHOLDS = {"advance": 75, "consider": 60}
STATUS_FROM_COVERAGE = {"demonstrated": "met", "listed": "partial", "absent": "not_met"}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def norm(s):
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", re.sub(r"[^\w%$+#'\"]+", " ", s)).strip()


def quote_found(quote, text_norm):
    parts = [norm(p) for p in re.split(r"\.\.\.|…", quote) if norm(p)]
    return bool(parts) and all(p in text_norm for p in parts)


# --------------------------------------------------------------------------- scoring


def integrity_tier(flags):
    s = sum(1 for f in flags if f.get("severity") == "strong")
    m = sum(1 for f in flags if f.get("severity") == "moderate")
    w = sum(1 for f in flags if f.get("severity") == "weak")
    if s or m >= 3:
        return "High risk"
    if m or w >= 3:
        return "Verify"
    return "Clear"


def score_candidate(sig, ev, reqs, weights, thresholds):
    text_norm = norm(sig.get("text", ""))
    dims, total, wsum, unverified = [], 0.0, 0, 0
    for key, label, desc in DIMENSIONS:
        d = (ev.get("dimensions") or {}).get(key) or {}
        raw = d.get("score")
        quotes = [{"text": q, "found": quote_found(q, text_norm)} for q in d.get("evidence", []) if q]
        unverified += sum(1 for q in quotes if not q["found"])
        used = raw
        capped = False
        if isinstance(raw, (int, float)) and raw >= 4 and not any(q["found"] for q in quotes):
            used, capped = 3, True
        w = weights.get(key, 0)
        if isinstance(used, (int, float)) and w:
            used = max(1, min(5, used))
            total += w * (used - 1) / 4
            wsum += w
        dims.append({"key": key, "label": label, "desc": desc, "weight": w, "score": raw, "used": used,
                     "capped": capped, "confidence": d.get("confidence", "low" if key == "work_style" else "medium"),
                     "rationale": d.get("rationale", ""), "quotes": quotes})
    score = round(100 * total / wsum) if wsum else 0

    cov = sig.get("coverage", {})
    req_status = {}
    for r in reqs:
        call = (ev.get("requirements") or {}).get(r["id"])
        scan = cov.get(r["id"], {}).get("status", "absent")
        req_status[r["id"]] = {"status": call or STATUS_FROM_COVERAGE[scan], "scanner": scan,
                               "reviewer": bool(call), "last_used": cov.get(r["id"], {}).get("last_used")}
    musts = [r for r in reqs if r.get("must")]
    missed = [r for r in musts if req_status[r["id"]]["status"] == "not_met"]
    partial = [r for r in musts if req_status[r["id"]]["status"] == "partial"]

    flags = list(sig.get("flags", [])) + [dict(f, source="reviewer") for f in ev.get("reviewer_flags", [])]
    order = {"strong": 0, "moderate": 1, "weak": 2}
    flags.sort(key=lambda f: order.get(f.get("severity"), 3))
    tier = integrity_tier(flags)
    if not sig.get("readable", True):
        rec = "Unreadable"
    elif tier == "High risk":
        rec = "Verify first"
    elif score >= thresholds["advance"] and not missed:
        rec = "Advance"
    elif score >= thresholds["consider"] and len(missed) <= 1:
        rec = "Consider"
    else:
        rec = "Pass"
    return {"id": sig["id"], "name": ev.get("name") or sig.get("contacts", {}).get("name_guess") or sig["id"],
            "headline": ev.get("headline", ""), "score": score, "dims": dims, "req_status": req_status,
            "musts_met": len(musts) - len(missed) - len(partial), "musts_partial": len(partial), "musts_total": len(musts), "missed": [r["label"] for r in missed],
            "flags": flags, "tier": tier, "rec": rec, "unverified_quotes": unverified,
            "strengths": ev.get("strengths", []), "gaps": ev.get("gaps", []),
            "questions": ev.get("interview_questions", []), "notes": ev.get("notes", ""), "sig": sig}


# --------------------------------------------------------------------------- html pieces

REC_STATUS = {"Advance": "good", "Consider": "warning", "Pass": "neutral", "Verify first": "critical",
              "Unreadable": "neutral"}
TIER_STATUS = {"Clear": "good", "Verify": "warning", "High risk": "critical"}
ICON = {"good": "✓", "warning": "!", "serious": "!", "critical": "✕", "neutral": "–"}
REQ_CELL = {"met": ("good", "✓", "Met"), "partial": ("warning", "◐", "Partial"),
            "not_met": ("critical", "✕", "Not met")}
CHECK = "\u2713"
SEV = {"strong": "critical", "moderate": "serious", "weak": "neutral"}


def chip(label, status, title=""):
    return (f'<span class="chip st-{status}" title="{esc(title)}"><span class="ic" aria-hidden="true">'
            f'{ICON.get(status, "")}</span>{esc(label)}</span>')


def ring(score, size=64):
    r = 26
    c = 2 * 3.14159 * r
    off = c * (1 - score / 100)
    return (f'<svg class="ring" width="{size}" height="{size}" viewBox="0 0 64 64" role="img" aria-label="Fit score {score}">'
            f'<circle cx="32" cy="32" r="{r}" class="ring-track"/>'
            f'<circle cx="32" cy="32" r="{r}" class="ring-val" stroke-dasharray="{c:.1f}" stroke-dashoffset="{off:.1f}" '
            f'transform="rotate(-90 32 32)"/><text x="32" y="37" text-anchor="middle">{score}</text></svg>')


def dim_rows(c):
    out = []
    for d in c["dims"]:
        s = d["used"]
        pct = 0 if not isinstance(s, (int, float)) else (s / 5) * 100
        cap = ' <span class="tag warn" title="Scored 4+ with no quote found in the application; counted as 3">capped</span>' if d["capped"] else ""
        conf = f'<span class="tag">{esc(d["confidence"])} confidence</span>'
        quotes = "".join(
            f'<li class="{"ok" if q["found"] else "miss"}"><span class="qi" title="'
            f'{"Quote found in the application" if q["found"] else "Quote NOT found in the application text"}">'
            f'{CHECK if q["found"] else "?"}</span>&ldquo;{esc(q["text"])}&rdquo;</li>' for q in d["quotes"])
        out.append(
            f'<div class="dim"><div class="dim-head"><span class="dim-label">{esc(d["label"])}</span>'
            f'<span class="dim-w">weight {d["weight"]}</span>{conf}{cap}'
            f'<span class="dim-s">{esc(s if s is not None else "n/a")}<small>/5</small></span></div>'
            f'<div class="bar" title="{esc(d["label"])}: {esc(s)}/5"><span style="width:{pct:.0f}%"></span></div>'
            f'<p class="why">{esc(d["rationale"])}</p>'
            + (f'<ul class="quotes">{quotes}</ul>' if quotes else "") + "</div>")
    return "".join(out)


def timeline_svg(tl):
    roles = tl.get("roles") or []
    if not roles:
        return '<p class="muted">No dated roles found in an experience section.</p>'
    now = date.today().year * 12 + date.today().month - 1
    lo = min(r["start"] for r in roles)
    lo = (lo // 12) * 12
    hi = max(now, max(r["end"] for r in roles)) + 1
    W, row, pad, left = 760, 22, 8, 22
    H = len(roles) * row + 34
    x = lambda m: left + (m - lo) / max(1, hi - lo) * (W - left - 22)
    parts = [f'<svg class="tl" viewBox="0 0 {W} {H}" role="img" aria-label="Career timeline">']
    for y in range(lo // 12, hi // 12 + 1):
        if (y - lo // 12) % max(1, (hi - lo) // 12 // 8 + 1) == 0:
            xx = x(y * 12)
            parts.append(f'<line class="grid" x1="{xx:.1f}" x2="{xx:.1f}" y1="0" y2="{H - 18}"/>'
                         f'<text class="axis" x="{xx:.1f}" y="{H - 4}" text-anchor="middle">{y}</text>')
    merged = sorted(roles, key=lambda r: r["start"])
    for i, r in enumerate(merged):
        y0 = i * row + pad
        x0, x1 = x(r["start"]), x(r["end"] + 1)
        cls = "role part" if r.get("partial") else "role"
        tip = f'{r["context"]} ({"partial/contract" if r.get("partial") else "full-time"})'
        parts.append(f'<g><title>{esc(tip)}</title><rect class="{cls}" x="{x0:.1f}" y="{y0}" width="{max(3, x1 - x0 - 2):.1f}" '
                     f'height="12" rx="4"/></g>')
    parts.append("</svg>")
    legend = ('<div class="legend"><span><i class="sw role"></i>Full-time role</span>'
              '<span><i class="sw part"></i>Contract / part-time / side</span></div>')
    facts = []
    for g in tl.get("gaps", []):
        facts.append(f'<li>Gap {esc(g["from"])} to {esc(g["to"])} ({g["months"]} mo). Neutral; ask only if relevant.</li>')
    for o in tl.get("overlaps", []):
        facts.append(f'<li class="warn">Overlap {o["months"]} mo: {esc(o["a"])} / {esc(o["b"])}</li>')
    return "".join(parts) + legend + (f'<ul class="tl-facts">{"".join(facts)}</ul>' if facts else "")


def flags_html(flags):
    if not flags:
        return '<p class="muted">No integrity signals found.</p>'
    rows = []
    for f in flags:
        st = SEV.get(f.get("severity"), "neutral")
        rows.append(
            f'<li class="flag"><div class="flag-h">{chip(f.get("severity", "").title(), st)}'
            f'<strong>{esc(f.get("title"))}</strong><span class="src">{esc(f.get("source", ""))}</span></div>'
            f'<div class="flag-b"><code>{esc(f.get("evidence"))}</code>'
            f'<p><b>Innocent read:</b> {esc(f.get("innocent_read"))}</p>'
            f'<p><b>Verify:</b> {esc(f.get("verify"))}</p></div></li>')
    return f'<ul class="flags">{"".join(rows)}</ul>'


def questions_html(qs):
    if not qs:
        return ""
    labels = {k: l for k, l, _ in DIMENSIONS}
    labels.update({"integrity": "Integrity", "gap": "Gaps"})
    items = "".join(f'<li><span class="tag">{esc(labels.get(q.get("area"), q.get("area", "")))}</span>{esc(q.get("question"))}</li>'
                    for q in qs)
    return f'<h4>Interview questions</h4><ol class="qs">{items}</ol>'


def musts_cell(c):
    extra = f' +{c["musts_partial"]} partial' if c.get("musts_partial") else ""
    return f'{c["musts_met"]}/{c["musts_total"]}{extra}'


def card(c, rank, reqs, open_):
    sig = c["sig"]
    tl = sig.get("timeline", {})
    wr = sig.get("writing", {})
    ct = sig.get("contacts", {})
    links = []
    for k in ("linkedin", "github"):
        if ct.get(k):
            u = ct[k] if ct[k].startswith("http") else "https://" + ct[k]
            links.append(f'<a href="{esc(u)}" rel="noopener noreferrer" target="_blank">{k.title()}</a>')
    facts = [
        ("Years (dated roles)", tl.get("years_total", "n/a")),
        ("Median tenure", f'{tl["median_tenure_months"]} mo' if tl.get("median_tenure_months") else "n/a"),
        ("Quantified bullets", f'{wr.get("quantified", 0)}/{wr.get("bullets", 0)}' if wr else "n/a"),
        ("Must-haves met", musts_cell(c)),
        ("Profiles", " ".join(links) or "none listed"),
    ]
    facts_html = "".join(f'<div class="fact"><span>{esc(k)}</span><b>{v if k == "Profiles" else esc(v)}</b></div>' for k, v in facts)
    buzz = wr.get("buzzwords") or []
    buzz_html = (f'<p class="muted small">Buzzwords: {esc(", ".join(buzz))}</p>' if len(buzz) >= 3 else "")
    reqs_html = "".join(
        f'<li>{chip(REQ_CELL[c["req_status"][r["id"]]["status"]][2], REQ_CELL[c["req_status"][r["id"]]["status"]][0])}'
        f'{"<b>MUST</b> " if r.get("must") else ""}{esc(r["label"])}'
        f'<span class="muted small"> scanner: {esc(c["req_status"][r["id"]]["scanner"])}'
        f'{", last used " + esc(c["req_status"][r["id"]]["last_used"]) if c["req_status"][r["id"]]["last_used"] else ""}'
        f'{" (reviewer call)" if c["req_status"][r["id"]]["reviewer"] else ""}</span></li>' for r in reqs)
    lst = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)
    return f'''
<details class="card" id="c-{esc(c["id"])}" data-rec="{esc(c["rec"])}" data-tier="{esc(c["tier"])}"{" open" if open_ else ""}>
<summary>
  <span class="rank">#{rank}</span>{ring(c["score"])}
  <span class="who"><b>{esc(c["name"])}</b><span class="muted">{esc(c["headline"])}</span></span>
  <span class="chips">{chip(c["rec"], REC_STATUS[c["rec"]])}{chip("Integrity: " + c["tier"], TIER_STATUS[c["tier"]])}</span>
</summary>
<div class="card-body">
  <div class="facts">{facts_html}</div>{buzz_html}
  {"<p class='alert'>Application could not be read well enough to score. See integrity signals.</p>" if not sig.get("readable", True) else ""}
  {f"<p class='alert'>{c['unverified_quotes']} evidence quote(s) were not found in the application text. Treat those claims as unverified.</p>" if c["unverified_quotes"] else ""}
  <div class="cols">
    <section><h4>Scorecard</h4>{dim_rows(c)}</section>
    <section>
      <h4>Strengths</h4><ul class="pros">{lst(c["strengths"]) or "<li class='muted'>None recorded</li>"}</ul>
      <h4>Gaps and risks</h4><ul class="cons">{lst(c["gaps"]) or "<li class='muted'>None recorded</li>"}</ul>
      <h4>Requirements</h4><ul class="reqs">{reqs_html}</ul>
    </section>
  </div>
  <h4>Career timeline</h4>{timeline_svg(tl)}
  <h4>Integrity signals</h4>{flags_html(c["flags"])}
  {questions_html(c["questions"])}
  {f'<h4>Reviewer notes</h4><p>{esc(c["notes"])}</p>' if c["notes"] else ""}
  <p class="muted small">Source file: {esc(Path(sig.get("file", "")).name)}</p>
</div>
</details>'''


def heatmap(cands, reqs):
    head = "".join(f'<th scope="col" title="{esc(r.get("text", r["label"]))}"><span>{esc(r["label"])}</span>'
                   f'{"<em>must</em>" if r.get("must") else ""}</th>' for r in reqs)
    rows = []
    for c in cands:
        cells = []
        for r in reqs:
            st = c["req_status"][r["id"]]
            k, g, lab = REQ_CELL[st["status"]]
            cells.append(f'<td class="hm st-{k}" title="{esc(c["name"])} / {esc(r["label"])}: {lab}'
                         f'{" (last used " + esc(st["last_used"]) + ")" if st["last_used"] else ""}">'
                         f'<span aria-label="{lab}">{g}</span></td>')
        rows.append(f'<tr><th scope="row"><a href="#c-{esc(c["id"])}">{esc(c["name"])}</a></th>{"".join(cells)}</tr>')
    return (f'<div class="hm-wrap"><table class="heat"><thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="legend">{chip("Met: done in a dated role", "good")}{chip("Partial: listed, not shown in a role", "warning")}'
            f'{chip("Not met", "critical")}</div>')


def leaderboard(cands):
    rows = []
    for i, c in enumerate(cands, 1):
        la = next((d["used"] for d in c["dims"] if d["key"] == "learning_agility"), None)
        rows.append(
            f'<tr data-rec="{esc(c["rec"])}" data-tier="{esc(c["tier"])}"><td class="num">{i}</td>'
            f'<td><a href="#c-{esc(c["id"])}"><b>{esc(c["name"])}</b></a><div class="muted small">{esc(c["headline"])}</div></td>'
            f'<td class="scorecell"><div class="sbar" title="Fit {c["score"]}/100"><span style="width:{c["score"]}%"></span></div>'
            f'<b class="num">{c["score"]}</b></td>'
            f'<td class="num">{musts_cell(c)}</td>'
            f'<td class="num">{esc(la if la is not None else "n/a")}</td>'
            f'<td>{chip(c["rec"], REC_STATUS[c["rec"]])}</td>'
            f'<td>{chip(c["tier"], TIER_STATUS[c["tier"]])}</td></tr>')
    return ('<div class="tbl-wrap"><table class="lb"><thead><tr><th>#</th><th>Candidate</th><th>Fit score</th>'
            '<th>Must-haves</th><th>Learning agility</th><th>Recommendation</th><th>Integrity</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


CSS = r"""
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--surface-2:#f0efec;--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6e69;
--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.10);--series:#2a78d6;--series-soft:#86b6ef;
--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;--good-ink:#006300;--warn-ink:#7a5200;--crit-ink:#a32020;
--hero-a:#0d366b;--hero-b:#2a78d6;--hero-c:#6250d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#262624;
--ink:#f0efec;--ink-2:#c3c2b7;--muted:#9a9890;--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--series:#3987e5;--series-soft:#1c5cab;
--good-ink:#0ca30c;--warn-ink:#fab219;--crit-ink:#e66767;--hero-a:#0d1f3c;--hero-b:#184f95;--hero-c:#4a3aa7}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#262624;--ink:#f0efec;--ink-2:#c3c2b7;--muted:#9a9890;
--grid:#2c2c2a;--axis:#383835;--border:rgba(255,255,255,.10);--series:#3987e5;--series-soft:#1c5cab;--good-ink:#0ca30c;--warn-ink:#fab219;
--crit-ink:#e66767;--hero-a:#0d1f3c;--hero-b:#184f95;--hero-c:#4a3aa7}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--series)}
.wrap{max-width:1180px;margin:0 auto;padding:0 16px 64px}
.hero{background:linear-gradient(120deg,var(--hero-a),var(--hero-b) 55%,var(--hero-c));color:#fff;padding:40px 0 88px}
.hero .wrap{padding-bottom:0}
.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:12px;opacity:.8;margin:0}
.hero h1{font-size:clamp(26px,4vw,40px);line-height:1.15;margin:8px 0 6px}
.hero p{margin:0;opacity:.9}
.toggle{float:right;background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:6px 12px;cursor:pointer;font:inherit;font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:-60px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px 18px;box-shadow:0 6px 24px rgba(0,0,0,.08)}
.kpi span{display:block;color:var(--ink-2);font-size:13px}
.kpi b{font-size:32px;line-height:1.1}
.kpi i{display:block;font-style:normal;font-size:12px;color:var(--muted)}
.kpi.k-good b{color:var(--good-ink)}.kpi.k-crit b{color:var(--crit-ink)}.kpi.k-warn b{color:var(--warn-ink)}
h2{font-size:20px;margin:40px 0 4px}
h2+p.sub{margin:0 0 14px;color:var(--ink-2)}
h4{margin:20px 0 8px;font-size:14px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-2)}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:16px}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 12px}
.filters button{font:inherit;font-size:13px;border:1px solid var(--border);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;cursor:pointer}
.filters button[aria-pressed="true"]{background:var(--ink);color:var(--page)}
.tbl-wrap,.hm-wrap{overflow-x:auto;background:var(--surface);border:1px solid var(--border);border-radius:14px}
table{border-collapse:collapse;width:100%}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--grid);vertical-align:middle}
thead th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:600}
tbody tr:last-child th,tbody tr:last-child td{border-bottom:0}
.num{font-variant-numeric:tabular-nums}
.lb a{color:var(--ink);text-decoration:none}.lb a:hover{text-decoration:underline}
.scorecell{min-width:170px;white-space:nowrap}
.sbar{display:inline-block;width:110px;height:8px;background:var(--surface-2);border-radius:4px;vertical-align:middle;margin-right:8px;overflow:hidden}
.sbar span{display:block;height:100%;background:var(--series);border-radius:4px}
.chip{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:2px 9px 2px 3px;border-radius:999px;border:1px solid var(--border);background:var(--surface);color:var(--ink);white-space:nowrap;margin:2px 4px 2px 0}
.chip .ic{display:inline-grid;place-items:center;width:17px;height:17px;border-radius:50%;font-size:11px;color:#fff;background:var(--muted)}
.st-good .ic{background:var(--good)}.st-warning .ic{background:var(--warning);color:#0b0b0b}.st-serious .ic{background:var(--serious);color:#0b0b0b}.st-critical .ic{background:var(--critical)}
.heat th[scope=col]{writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap;height:auto;min-height:100px;vertical-align:bottom;padding:8px 4px;text-transform:none;letter-spacing:0;font-size:12px;color:var(--ink-2)}
.heat th[scope=col] span,.heat th[scope=col] em{display:block}
.heat th[scope=col] em{font-style:normal;font-size:10px;font-weight:700;color:var(--crit-ink);margin:0 2px 0 0}
.heat th[scope=row]{white-space:nowrap;font-weight:600}
.heat th[scope=row] a{color:var(--ink);text-decoration:none}
.hm{text-align:center;padding:4px}
.hm span{display:inline-grid;place-items:center;width:30px;height:26px;border-radius:5px;font-weight:700;font-size:13px}
.hm.st-good span{background:color-mix(in srgb,var(--good) 22%,transparent);color:var(--good-ink)}
.hm.st-warning span{background:color-mix(in srgb,var(--warning) 28%,transparent);color:var(--warn-ink)}
.hm.st-critical span{background:color-mix(in srgb,var(--critical) 18%,transparent);color:var(--crit-ink)}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin:10px 0 0;font-size:12px;color:var(--ink-2)}
.legend .sw{display:inline-block;width:14px;height:8px;border-radius:3px;margin-right:6px;vertical-align:middle}
.sw.role{background:var(--series)}.sw.part{background:var(--series-soft)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;margin:12px 0;overflow:hidden}
.card summary{display:flex;align-items:center;gap:14px;padding:14px 16px;cursor:pointer;list-style:none;flex-wrap:wrap}
.card summary::-webkit-details-marker{display:none}
.card[open] summary{border-bottom:1px solid var(--grid)}
.rank{font-weight:700;color:var(--muted);width:30px}
.who{display:flex;flex-direction:column;flex:1;min-width:200px}
.who b{font-size:17px}
.chips{display:flex;flex-wrap:wrap}
.ring-track{fill:none;stroke:var(--surface-2);stroke-width:7}
.ring-val{fill:none;stroke:var(--series);stroke-width:7;stroke-linecap:round}
.ring text{font-size:17px;font-weight:700;fill:var(--ink)}
.card-body{padding:4px 16px 18px}
.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-top:12px}
.fact{background:var(--surface-2);border-radius:10px;padding:8px 12px}
.fact span{display:block;font-size:12px;color:var(--ink-2)}
.fact a{margin-right:8px}
.cols{display:grid;grid-template-columns:1.25fr 1fr;gap:24px}
@media (max-width:820px){.cols{grid-template-columns:1fr}}
.dim{padding:10px 0;border-bottom:1px solid var(--grid)}
.dim:last-child{border-bottom:0}
.dim-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.dim-label{font-weight:600}
.dim-w{font-size:12px;color:var(--muted)}
.dim-s{margin-left:auto;font-weight:700;font-size:18px}.dim-s small{font-size:12px;color:var(--muted);font-weight:400}
.tag{font-size:11px;padding:1px 7px;border-radius:999px;background:var(--surface-2);color:var(--ink-2);margin-right:6px}
.tag.warn{background:color-mix(in srgb,var(--warning) 30%,transparent);color:var(--warn-ink)}
.bar{height:8px;background:var(--surface-2);border-radius:4px;margin:6px 0;overflow:hidden}
.bar span{display:block;height:100%;background:var(--series);border-radius:4px}
.why{margin:4px 0;color:var(--ink-2);font-size:14px}
.quotes{list-style:none;padding:0;margin:4px 0 0;font-size:13px}
.quotes li{display:flex;gap:6px;padding:3px 0;color:var(--ink-2);font-style:italic}
.quotes .qi{font-style:normal;font-weight:700;width:16px;flex:none}
.quotes .ok .qi{color:var(--good-ink)}.quotes .miss{color:var(--crit-ink)}.quotes .miss .qi{color:var(--crit-ink)}
.pros li::marker{color:var(--good-ink)}.cons li::marker{color:var(--crit-ink)}
ul.pros,ul.cons{padding-left:18px;margin:0}ul.pros li,ul.cons li{margin:3px 0}
.reqs{list-style:none;padding:0;margin:0}.reqs li{padding:3px 0;font-size:14px}.reqs b{font-size:10px;color:var(--crit-ink);margin-right:4px}
.tl{width:100%;height:auto;display:block}
.tl .grid{stroke:var(--grid);stroke-width:1}
.tl .axis{fill:var(--muted);font-size:11px}
.tl .role{fill:var(--series)}.tl .part{fill:var(--series-soft)}
.tl-facts{font-size:13px;color:var(--ink-2);padding-left:18px}.tl-facts .warn{color:var(--crit-ink)}
.flags{list-style:none;padding:0;margin:0}
.flag{border:1px solid var(--border);border-radius:10px;padding:10px 12px;margin:8px 0}
.flag-h{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.flag .src{margin-left:auto;font-size:11px;color:var(--muted)}
.flag code{display:block;margin:8px 0;padding:8px;border-radius:6px;background:var(--surface-2);font-size:12px;white-space:pre-wrap;word-break:break-word}
.flag p{margin:3px 0;font-size:13px;color:var(--ink-2)}
.qs{padding-left:20px}.qs li{margin:6px 0}
.alert{background:color-mix(in srgb,var(--critical) 12%,transparent);border-left:3px solid var(--critical);padding:8px 12px;border-radius:6px;font-size:14px}
.muted{color:var(--muted)}.small{font-size:12px}
.method{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.method ul{padding-left:18px;margin:6px 0}.method li{margin:4px 0;font-size:14px}
.weights td{padding:6px 8px;font-size:14px}
.hidden-row{display:none}
@media (max-width:640px){.hero{padding:28px 0 76px}.toggle{float:none;margin-bottom:12px}
.lb .muted.small,.lb th:nth-child(5),.lb td:nth-child(5){display:none}.sbar{width:56px}.scorecell{min-width:0}
th,td{padding:8px}.card summary{gap:10px}.rank{width:auto}.kpi b{font-size:26px}}
footer{margin-top:40px;font-size:12px;color:var(--muted)}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.toolbar button{font:inherit;font-size:13px;font-weight:600;background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:6px 14px;cursor:pointer}
.toolbar button:hover{background:rgba(255,255,255,.28)}
@media print{html:root:not([data-print-none]),html:root[data-theme]{color-scheme:light;--page:#fff;--surface:#fff;--surface-2:#f0efec;
--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6e69;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.12);--series:#2a78d6;--series-soft:#86b6ef;
--good-ink:#006300;--warn-ink:#7a5200;--crit-ink:#a32020}
body{-webkit-print-color-adjust:exact;print-color-adjust:exact}
@page{size:letter;margin:12mm}
.hero{background:none;color:#000;padding:16px 0}.toggle,.filters,.toolbar{display:none}
.kpis{margin-top:0;grid-template-columns:repeat(5,1fr)}.kpi{box-shadow:none;padding:10px 12px}.kpi b{font-size:24px}
.lb .muted.small{display:none}.lb td,.lb th{padding:6px 8px}.sbar{width:70px}.scorecell{min-width:0}h2{break-after:avoid}
.card{break-inside:avoid}details.card>.card-body{display:block}}
"""

JS = r"""
(function(){
  var root=document.documentElement,btn=document.getElementById('theme');
  try{var t=localStorage.getItem('cs-theme');if(t)root.setAttribute('data-theme',t);}catch(e){}
  btn.addEventListener('click',function(){
    var dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme: dark)').matches);
    var next=dark?'light':'dark';root.setAttribute('data-theme',next);try{localStorage.setItem('cs-theme',next);}catch(e){}
  });
  var fb=document.querySelectorAll('.filters button');
  fb.forEach(function(b){b.addEventListener('click',function(){
    fb.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false')});
    var f=b.dataset.f;
    document.querySelectorAll('[data-rec]').forEach(function(el){
      var show=f==='all'||el.dataset.rec===f||(f==='flagged'&&el.dataset.tier!=='Clear');
      el.classList.toggle('hidden-row',!show);
    });
  })});
  function openAll(){document.querySelectorAll('details.card').forEach(function(d){d.open=true})}
  window.addEventListener('beforeprint',openAll);
  if(location.hash==='#print')openAll();
  var inFrame=false;try{inFrame=window.self!==window.top}catch(e){inFrame=true}
  var tb=document.getElementById('toolbar');if(inFrame&&tb)tb.style.display='none';
  var meta={};try{meta=JSON.parse(document.getElementById('cs-data').textContent)}catch(e){}
  function dl(name,type,data){var b=new Blob([data],{type:type}),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=name;
    document.body.appendChild(a);a.click();setTimeout(function(){URL.revokeObjectURL(a.href);a.remove()},1000)}
  function on(id,fn){var el=document.getElementById(id);if(el)el.addEventListener('click',fn)}
  on('dl-html',function(){var c=root.cloneNode(true);c.removeAttribute('data-theme');
    c.querySelectorAll('.hidden-row').forEach(function(el){el.classList.remove('hidden-row')});
    dl(meta.base+'.html','text/html','<!doctype html>\n'+c.outerHTML)});
  on('dl-csv',function(){dl(meta.base+'.csv','text/csv','\ufeff'+meta.csv)});
  on('dl-pdf',function(){openAll();window.print()});
})();
"""

SOURCES = [
    ("Sackett et al. 2022, revisiting meta-analytic validity of selection procedures (J. Applied Psychology)",
     "https://ink.library.smu.edu.sg/lkcsb_research/6894"),
    ("SIOP: is cognitive ability the best predictor of job performance?",
     "https://www.siop.org/tip-article/is-cognitive-ability-the-best-predictor-of-job-performance"),
    ("BPS Research Digest: recruiters think they can read personality from a resume; they can't",
     "https://bps.org.uk/research-digest/recruiters-think-they-can-tell-your-personality-your-resume-they-cant"),
    ("Hartel et al. 2024: resume cues and applicant personality", "https://cris-portal.uni-muenster.de/portal/en/publication/98372028"),
    ("FBI IC3 PSA I-101326 (Oct 2026): North Korean IT worker indicators and mitigations", "https://www.ic3.gov/PSA/2026/PSA261013"),
    ("FBI IC3 PSA I-012325 (Jan 2025): reused contacts, resume nomenclature, face-swap interviews",
     "https://www.ic3.gov/psa/2025/psa250123"),
    ("HR Dive: Gartner, 1 in 4 candidate profiles could be fake by 2028", "https://www.hrdive.com/news/fake-job-candidates-ai/757126/"),
    ("Metaview: resume prompt injection", "https://www.metaview.ai/resources/blog/resume-prompt-injection"),
    ("SHRM: verify degrees, resume fraud", "https://shrm.org/topics-tools/news/talent-acquisition/verify-degrees-protect-company-resume-fraud"),
    ("Jackson Lewis: using AI to speed through candidates, legal risks",
     "https://www.jacksonlewis.com/insights/using-ai-speed-through-candidates-slow-down-and-consider-risks"),
]


RANK_KEY = {"Advance": 0, "Consider": 1, "Verify first": 2, "Pass": 3, "Unreadable": 4}


def compute(signals, evals, req):
    """Score every candidate and return them in report order."""
    reqs = req.get("requirements", [])
    weights = {**DEFAULT_WEIGHTS, **req.get("weights", {})}
    thresholds = {**DEFAULT_THRESHOLDS, **req.get("thresholds", {})}
    ev_by = {e["id"]: e for e in evals.get("candidates", [])}
    cands = [score_candidate(s, ev_by.get(s["id"], {}), reqs, weights, thresholds) for s in signals["candidates"]]
    cands.sort(key=lambda c: (RANK_KEY[c["rec"]], -c["score"]))
    return cands, reqs, weights, thresholds, ev_by


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def report_basename(req, signals):
    parts = [req.get("company", ""), req.get("role", "role"), "candidate-screen", signals.get("generated", "")]
    return "-".join(p for p in (slug(x) for x in parts) if p)[:120]


CSV_COLS = ["rank", "name", "fit_score", "recommendation", "integrity", "must_haves_met", "must_haves_partial",
            "must_haves_total", "missed_must_haves", "must_have", "experience", "impact", "learning_agility",
            "work_style", "nice_to_have", "top_integrity_flag", "headline", "source_file"]


def csv_rows(cands):
    rows = []
    for i, c in enumerate(cands, 1):
        d = {x["key"]: x["used"] for x in c["dims"]}
        top = next((f.get("title") for f in c["flags"] if f.get("severity") in ("strong", "moderate")), "")
        rows.append({"rank": i, "name": c["name"], "fit_score": c["score"], "recommendation": c["rec"],
                     "integrity": c["tier"], "must_haves_met": c["musts_met"], "must_haves_partial": c["musts_partial"],
                     "must_haves_total": c["musts_total"], "missed_must_haves": "; ".join(c["missed"]),
                     **{k: d.get(k) for k in DEFAULT_WEIGHTS}, "top_integrity_flag": top, "headline": c["headline"],
                     "source_file": Path(c["sig"].get("file", "")).name})
    return rows


def csv_cell(v):
    """Neutralize spreadsheet formulas: application text is untrusted (CSV injection)."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def to_csv(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_COLS, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: csv_cell(r.get(k)) for k in CSV_COLS})
    return buf.getvalue()


CHROME_PATHS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]


def find_chrome():
    for p in CHROME_PATHS:
        if Path(p).exists():
            return p
    for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"):
        w = shutil.which(n)
        if w:
            return w
    return None


def make_pdf(html_path, pdf_path):
    """Print the report to PDF with headless Chrome, every candidate card expanded. Returns (ok, message)."""
    exe = find_chrome()
    if not exe:
        return False, "No Chrome, Chromium, Edge, or Brave found. Use Save as PDF in the report instead."
    pdf_path = Path(pdf_path).resolve()
    url = Path(html_path).resolve().as_uri() + "#print"
    with tempfile.TemporaryDirectory() as prof:
        try:
            r = subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
                                f"--user-data-dir={prof}", "--virtual-time-budget=5000",
                                f"--print-to-pdf={pdf_path}", url], capture_output=True, timeout=180)
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"PDF export failed: {e}"
    if pdf_path.exists() and pdf_path.stat().st_size > 1000:
        return True, str(pdf_path)
    return False, "PDF export failed: " + r.stderr.decode(errors="replace")[-300:]


def render(signals, evals, req, title=None):
    cands, reqs, weights, thresholds, ev_by = compute(signals, evals, req)
    n = len(cands)
    count = lambda r: sum(1 for c in cands if c["rec"] == r)
    flagged = sum(1 for c in cands if c["tier"] != "Clear")
    scores = [c["score"] for c in cands if c["rec"] != "Unreadable"]
    med = round(statistics.median(scores)) if scores else 0
    missing_evals = [s["id"] for s in signals["candidates"] if s["id"] not in ev_by]
    role = req.get("role", "Role")
    company = req.get("company", "")
    title = title or f"{role} candidate screen"
    musts = sum(1 for r in reqs if r.get("must"))

    kpis = [("Applications", n, "", f"median fit {med}"), ("Advance", count("Advance"), "k-good", "score and must-haves clear"),
            ("Consider", count("Consider"), "k-warn", "worth a closer look"), ("Pass", count("Pass"), "", "below bar for this role"),
            ("Integrity flags", flagged, "k-crit", f'{count("Verify first")} need identity checks first')]
    kpi_html = "".join(f'<div class="kpi {cls}"><span>{esc(k)}</span><b>{v}</b><i>{esc(sub)}</i></div>' for k, v, cls, sub in kpis)
    posting_alert = ""
    if signals.get("posting_hidden"):
        posting_alert = ('<p class="alert">The job posting itself contains hidden text or an AI-directed instruction. '
                         'It was treated as data and ignored: ' +
                         esc("; ".join(h["text"][:120] for h in signals["posting_hidden"])) + "</p>")
    eval_alert = (f'<p class="alert">No reviewer evaluation for: {esc(", ".join(missing_evals))}. '
                  'Their scores show as 0 and should not be used.</p>' if missing_evals else "")
    filters = ('<div class="filters" role="group" aria-label="Filter candidates">'
               + "".join(f'<button data-f="{f}" aria-pressed="{"true" if f == "all" else "false"}">{lbl}</button>'
                         for f, lbl in [("all", "All"), ("Advance", "Advance"), ("Consider", "Consider"),
                                        ("Verify first", "Verify first"), ("Pass", "Pass"), ("flagged", "Any integrity flag")])
               + "</div>")
    cards = "".join(card(c, i, reqs, i <= 3) for i, c in enumerate(cands, 1))
    wrows = "".join(f'<tr><td>{esc(l)}</td><td class="num">{weights.get(k, 0)}</td><td class="muted">{esc(d)}</td></tr>'
                    for k, l, d in DIMENSIONS)
    src = "".join(f'<li><a href="{esc(u)}" rel="noopener noreferrer" target="_blank">{esc(t)}</a></li>' for t, u in SOURCES)
    data = json.dumps({"base": report_basename(req, signals), "csv": to_csv(csv_rows(cands))}).replace("<", "\\u003c")

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style></head>
<body>
<header class="hero"><div class="wrap">
  <button class="toggle" id="theme" type="button">Light / dark</button>
  <p class="eyebrow">Candidate screen{" / " + esc(company) if company else ""} / {esc(signals.get("generated", ""))}</p>
  <h1>{esc(role)}</h1>
  <p>{n} application{"s" if n != 1 else ""} scored against {len(reqs)} requirements ({musts} must-have). Fit and integrity are scored separately. A person makes every decision.</p>
  <div class="toolbar" id="toolbar"><button id="dl-pdf" type="button">Save as PDF</button><button id="dl-html" type="button">Download HTML</button><button id="dl-csv" type="button">Download CSV</button></div>
</div></header>
<main class="wrap">
  <div class="kpis">{kpi_html}</div>
  {posting_alert}{eval_alert}
  <h2>Shortlist</h2><p class="sub">Ranked by recommendation, then fit score. Learning agility is shown on its own because it predicts ramp-up on what they do not know yet.</p>
  {filters}{leaderboard(cands)}
  <h2>Requirement coverage</h2><p class="sub">Met means the skill shows up inside a dated role, not just a skills list.</p>
  {heatmap(cands, reqs)}
  <h2>Candidates</h2><p class="sub">Every score carries a rationale and quotes. A check mark means the quote was found in the application; a question mark means it was not.</p>
  {cards}
  <h2>How this was scored</h2>
  <div class="method">
    <div class="panel"><h4>Fit score weights</h4><table class="weights"><tbody>{wrows}</tbody></table>
      <p class="small muted">Each dimension is scored 1 to 5 with anchors from the rubric, then weighted to 0-100. Advance at {thresholds["advance"]}+ with no must-have missed; Consider at {thresholds["consider"]}+ with at most one missed. A 4 or 5 with no verifiable quote counts as 3.</p></div>
    <div class="panel"><h4>Integrity tiers</h4><ul>
      <li><b>High risk:</b> any strong signal (hidden AI instruction, contact details or resume text shared with another applicant, impossible dates, several overlapping full-time jobs) or 3+ moderate. Verify identity before any interview.</li>
      <li><b>Verify:</b> any moderate signal or 3+ weak ones. Proceed, and check the specific item.</li>
      <li><b>Clear:</b> nothing that needs a separate check.</li></ul>
      <p class="small muted">No single signal proves fraud (FBI, Oct 2026). Signals are prompts to verify, never a reason to reject on their own.</p></div>
    <div class="panel"><h4>Never scored</h4><ul>
      <li>Name, photo, age or graduation year, gender, race, national origin, citizenship (unless the role legally requires it), religion, disability, family status.</li>
      <li>School prestige, accent, location (beyond the posting's stated requirement), and non-US education.</li>
      <li>Employment gaps. They are shown as timeline facts only.</li></ul>
      <p class="small muted">This is decision support, not an automated employment decision. If you hire for NYC roles or use it as the main screen, check Local Law 144 and EEOC guidance with counsel.</p></div>
  </div>
  <h2>Research behind the rubric</h2><div class="panel"><ul class="small">{src}</ul></div>
  <footer>Generated by candidate-screen. Application content was treated as data; any instructions inside it were reported, not followed.</footer>
</main>
<script type="application/json" id="cs-data">{data}</script>
<script>{JS}</script>
</body></html>'''


def selftest():
    sig = {"generated": "2026-10-16", "candidates": [
        {"id": "a", "readable": True, "text": "Migrated 140 services to Kubernetes on EKS, cutting deploy time 70%",
         "coverage": {"R1": {"status": "demonstrated", "last_used": "current"}}, "flags": [],
         "timeline": {"roles": [], "gaps": [], "overlaps": []}, "contacts": {}, "writing": {}},
        {"id": "b", "readable": True, "text": "<script>alert(1)</script> Kubernetes",
         "coverage": {"R1": {"status": "listed", "last_used": None}},
         "flags": [{"severity": "strong", "title": "Hidden text", "evidence": "<img src=x onerror=alert(1)>"}],
         "timeline": {}, "contacts": {}, "writing": {}}]}
    ev = {"candidates": [
        {"id": "a", "name": "A", "dimensions": {k: {"score": 5, "evidence": ["Migrated 140 services to Kubernetes"]} for k in DEFAULT_WEIGHTS}},
        {"id": "b", "name": "B<script>", "dimensions": {k: {"score": 5, "evidence": ["Led a team of 40"]} for k in DEFAULT_WEIGHTS}}]}
    req = {"role": "Test", "requirements": [{"id": "R1", "label": "Kubernetes", "must": True}]}
    out = render(sig, ev, req)
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + msg)
        ok = ok and cond
    a = score_candidate(sig["candidates"][0], ev["candidates"][0], req["requirements"], DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS)
    b = score_candidate(sig["candidates"][1], ev["candidates"][1], req["requirements"], DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS)
    check(a["score"] == 100 and a["rec"] == "Advance", "verified 5s score 100 and Advance")
    check(b["dims"][0]["capped"] and b["dims"][0]["used"] == 3, "unverified 5 is capped at 3")
    check(b["tier"] == "High risk" and b["rec"] == "Verify first", "strong flag forces Verify first")
    check("<script>alert" not in out and "onerror=alert" not in out.replace("&lt;img src=x onerror=alert(1)&gt;", ""),
          "application text is escaped")
    check(quote_found("cutting deploy time ... 70%", norm(sig["candidates"][0]["text"])), "ellipsis quotes match by part")
    rows = csv_rows(compute(sig, ev, req)[0])
    rows[0]["headline"] = "=HYPERLINK(\"http://x\")"
    out_csv = to_csv(rows)
    check("'=HYPERLINK" in out_csv and "\n=HYPERLINK" not in out_csv, "CSV neutralizes formulas from application text")
    check("</script><script>" not in out.split('id="cs-data">')[1].split("</script>")[0] + "x", "embedded data cannot close its script tag")
    print("all passed" if ok else "FAILURES")
    return 0 if ok else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--signals", required=True)
    ap.add_argument("--evals", required=True)
    ap.add_argument("--requirements", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--json", help="also write the computed scores here")
    ap.add_argument("--csv", help="also write the shortlist as CSV here")
    ap.add_argument("--pdf", help="also print the report to PDF here (needs Chrome, Chromium, Edge, or Brave)")
    a = ap.parse_args()
    signals = json.loads(Path(a.signals).read_text())
    evals = json.loads(Path(a.evals).read_text())
    req = json.loads(Path(a.requirements).read_text())
    Path(a.out).write_text(render(signals, evals, req, a.title))
    print(f"report -> {a.out}")
    if a.csv:
        Path(a.csv).write_text("\ufeff" + to_csv(csv_rows(compute(signals, evals, req)[0])))
        print(f"csv -> {a.csv}")
    if a.pdf:
        ok, msg = make_pdf(a.out, a.pdf)
        print(f"pdf -> {msg}" if ok else msg)
    if a.json:
        reqs = req.get("requirements", [])
        weights = {**DEFAULT_WEIGHTS, **req.get("weights", {})}
        th = {**DEFAULT_THRESHOLDS, **req.get("thresholds", {})}
        ev_by = {e["id"]: e for e in evals.get("candidates", [])}
        rows = []
        for s in signals["candidates"]:
            c = score_candidate(s, ev_by.get(s["id"], {}), reqs, weights, th)
            rows.append({k: c[k] for k in ("id", "name", "score", "rec", "tier", "musts_met", "musts_partial", "musts_total",
                                           "missed", "unverified_quotes")})
        rows.sort(key=lambda r: -r["score"])
        Path(a.json).write_text(json.dumps(rows, indent=2))
        for r in rows:
            print(f'  {r["score"]:>3}  {r["rec"]:<13} {r["tier"]:<10} {r["name"]}')


if __name__ == "__main__":
    main()
