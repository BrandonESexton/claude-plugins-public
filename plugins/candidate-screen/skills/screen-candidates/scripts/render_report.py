#!/usr/bin/env python3
"""render_report: score a screened stack and render a self-contained HTML report.

  render_report.py --signals signals.json --evals evals.json --requirements requirements.json \
                   --out report.html [--title "..."] [--json scores.json]
  render_report.py ... [--csv shortlist.csv] [--pdf report.pdf] [--markdown summary.md]
  render_report.py welcome [--posting NAME] [--apps N]   chat card: step 1, what to send
  render_report.py requirements-md REQ.json [--page review.html]   chat card: step 2, plus the interactive review page
  render_report.py apply-changes REQ.json CHANGES|-       apply a reply from the review page (or written from chat)
  render_report.py scan-md signals.json REQ.json          chat card: step 3, scan results
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
    score = int(100 * total / wsum + 0.5) if wsum else 0  # half-up, same as the report's live rescoring

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
    facts_html = "".join(f'<div class="fact"><span>{esc(k)}</span><b{" class=js-musts" if k == "Must-haves met" else ""}>'
                         f'{v if k == "Profiles" else esc(v)}</b></div>' for k, v in facts)
    buzz = wr.get("buzzwords") or []
    buzz_html = (f'<p class="muted small">Buzzwords: {esc(", ".join(buzz))}</p>' if len(buzz) >= 3 else "")
    reqs_html = "".join(
        f'<li>{chip(REQ_CELL[c["req_status"][r["id"]]["status"]][2], REQ_CELL[c["req_status"][r["id"]]["status"]][0])}'
        f'<b class="mustlbl" data-req="{esc(r["id"])}"{"" if r.get("must") else " hidden"}>MUST</b> {esc(r["label"])}'
        f'<span class="muted small"> scanner: {esc(c["req_status"][r["id"]]["scanner"])}'
        f'{", last used " + esc(c["req_status"][r["id"]]["last_used"]) if c["req_status"][r["id"]]["last_used"] else ""}'
        f'{" (reviewer call)" if c["req_status"][r["id"]]["reviewer"] else ""}</span></li>' for r in reqs)
    lst = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)
    return f'''
<details class="card" id="c-{esc(c["id"])}" data-rec="{esc(c["rec"])}" data-tier="{esc(c["tier"])}"{" open" if open_ else ""}>
<summary>
  <span class="rank js-rank">#{rank}</span>{ring(c["score"])}
  <span class="who"><b>{esc(c["name"])}</b><span class="muted">{esc(c["headline"])}</span></span>
  <span class="chips"><span class="js-rec">{chip(c["rec"], REC_STATUS[c["rec"]])}</span>{chip("Integrity: " + c["tier"], TIER_STATUS[c["tier"]])}</span>
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
                   f'<em data-req="{esc(r["id"])}"{"" if r.get("must") else " hidden"}>must</em></th>' for r in reqs)
    rows = []
    for c in cands:
        cells = []
        for r in reqs:
            st = c["req_status"][r["id"]]
            k, g, lab = REQ_CELL[st["status"]]
            cells.append(f'<td class="hm st-{k}" title="{esc(c["name"])} / {esc(r["label"])}: {lab}'
                         f'{" (last used " + esc(st["last_used"]) + ")" if st["last_used"] else ""}">'
                         f'<span aria-label="{lab}">{g}</span></td>')
        rows.append(f'<tr data-id="{esc(c["id"])}"><th scope="row"><a href="#c-{esc(c["id"])}">{esc(c["name"])}</a></th>{"".join(cells)}</tr>')
    return (f'<div class="hm-wrap"><table class="heat"><thead><tr><th></th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>'
            f'<div class="legend">{chip("Met: done in a dated role", "good")}{chip("Partial: listed, not shown in a role", "warning")}'
            f'{chip("Not met", "critical")}</div>')


def leaderboard(cands):
    rows = []
    for i, c in enumerate(cands, 1):
        la = next((d["used"] for d in c["dims"] if d["key"] == "learning_agility"), None)
        rows.append(
            f'<tr data-id="{esc(c["id"])}" data-rec="{esc(c["rec"])}" data-tier="{esc(c["tier"])}"><td class="num js-rank">{i}</td>'
            f'<td><a href="#c-{esc(c["id"])}"><b>{esc(c["name"])}</b></a><div class="muted small">{esc(c["headline"])}</div></td>'
            f'<td class="scorecell"><div class="sbar" title="Fit {c["score"]}/100"><span style="width:{c["score"]}%"></span></div>'
            f'<b class="num js-score">{c["score"]}</b></td>'
            f'<td class="num js-musts">{musts_cell(c)}</td>'
            f'<td class="num">{esc(la if la is not None else "n/a")}</td>'
            f'<td class="js-rec">{chip(c["rec"], REC_STATUS[c["rec"]])}</td>'
            f'<td>{chip(c["tier"], TIER_STATUS[c["tier"]])}</td>'
            f'<td class="cmpcell"><label class="cmp" title="Compare side by side"><input type="checkbox" value="{esc(c["id"])}">'
            f'<span>Compare</span></label></td></tr>')
    return ('<div class="tbl-wrap"><table class="lb"><thead><tr><th>#</th><th>Candidate</th><th>Fit score</th>'
            '<th>Must-haves</th><th>Learning agility</th><th>Recommendation</th><th>Integrity</th><th class="cmpcell"></th></tr></thead>'
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
[hidden]{display:none!important}
.tune{margin:0 0 14px}.tune summary{cursor:pointer;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;list-style:none}
.tune summary::-webkit-details-marker{display:none}.tune summary b{font-size:16px}.tune summary b:before{content:"\25B8  ";color:var(--muted)}
.tune[open] summary b:before{content:"\25BE  "}
.tune-grid{display:grid;grid-template-columns:1.2fr 1fr;gap:24px;margin-top:6px}@media(max-width:820px){.tune-grid{grid-template-columns:1fr}}
.sliders{display:grid;grid-template-columns:1fr 1fr;gap:10px 20px}@media(max-width:520px){.sliders{grid-template-columns:1fr}}
.tw label{display:flex;justify-content:space-between;font-size:13px;font-weight:600}.tw output{font-variant-numeric:tabular-nums;color:var(--ink-2)}
.tw input{width:100%;accent-color:var(--series)}
.mtoggles{display:flex;flex-wrap:wrap;gap:6px}
.mt{font:inherit;font-size:12px;border:1px solid var(--border);background:var(--surface);color:var(--ink-2);border-radius:999px;padding:4px 10px;cursor:pointer}
.mt[aria-pressed="true"]{background:color-mix(in srgb,var(--critical) 14%,transparent);border-color:color-mix(in srgb,var(--critical) 45%,transparent);color:var(--crit-ink);font-weight:600}
.mt[aria-pressed="true"]:before{content:"MUST  ";font-size:10px;font-weight:700}
.thr{display:flex;gap:16px;flex-wrap:wrap;font-size:13px}.thr input{width:70px;font:inherit;padding:4px 8px;border:1px solid var(--border);border-radius:8px;background:var(--page);color:var(--ink);margin-left:6px}
.tune-note{display:flex;align-items:center;gap:12px;flex-wrap:wrap;background:color-mix(in srgb,var(--warning) 18%,transparent);border-left:3px solid var(--warning);border-radius:8px;padding:8px 12px;margin:0 0 14px;font-size:13px}
.tune-note button,#cmp-clear{font:inherit;font-size:12px;font-weight:600;border:1px solid var(--border);background:var(--surface);color:var(--ink);border-radius:999px;padding:3px 10px;cursor:pointer;margin-left:auto}
.cmpcell{white-space:nowrap}.cmp{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--ink-2);cursor:pointer}.cmp input{accent-color:var(--series)}
.compare{margin-top:12px}.cmp-head{display:flex;align-items:baseline;gap:10px;margin-bottom:8px}
.cmp-t th[scope=row]{width:26%;font-size:13px;font-weight:600;color:var(--ink-2)}.cmp-t td{width:37%;font-size:14px}.cmp-t ul{margin:0;padding-left:16px}
.cmp-t td.best{background:color-mix(in srgb,var(--good) 10%,transparent)}
.mini{display:inline-block;width:60px;height:6px;background:var(--surface-2);border-radius:3px;margin-right:8px;vertical-align:middle;overflow:hidden}
.mini span{display:block;height:100%;background:var(--series)}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.toolbar button{font:inherit;font-size:13px;font-weight:600;background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:6px 14px;cursor:pointer}
.toolbar button:hover{background:rgba(255,255,255,.28)}
@media print{html:root:not([data-print-none]),html:root[data-theme]{color-scheme:light;--page:#fff;--surface:#fff;--surface-2:#f0efec;
--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6e69;--grid:#e1e0d9;--axis:#c3c2b7;--border:rgba(11,11,11,.12);--series:#2a78d6;--series-soft:#86b6ef;
--good-ink:#006300;--warn-ink:#7a5200;--crit-ink:#a32020}
body{-webkit-print-color-adjust:exact;print-color-adjust:exact}
@page{size:letter;margin:12mm}
.hero{background:none;color:#000;padding:16px 0}.screen-only,.toggle,.filters,.toolbar,.tune,.tune-note button,.cmpcell,.compare{display:none}
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
  var fb=document.querySelectorAll('.filters button'),curF='all';
  function filt(){document.querySelectorAll('[data-rec]').forEach(function(el){
    var show=curF==='all'||el.dataset.rec===curF||(curF==='flagged'&&el.dataset.tier!=='Clear');
    el.classList.toggle('hidden-row',!show);})}
  fb.forEach(function(b){b.addEventListener('click',function(){
    fb.forEach(function(x){x.setAttribute('aria-pressed',x===b?'true':'false')});curF=b.dataset.f;filt();
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
  // ---------------------------------------------------------------- live rescoring
  var D=meta,RK={'Advance':0,'Consider':1,'Verify first':2,'Pass':3,'Unreadable':4};
  var RS={'Advance':'good','Consider':'warning','Pass':'neutral','Verify first':'critical','Unreadable':'neutral'};
  var TS={'Clear':'good','Verify':'warning','High risk':'critical'};
  var IC={good:'✓',warning:'!',critical:'✕',neutral:'–'};
  function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
  function chip(l,st){return '<span class="chip st-'+st+'"><span class="ic" aria-hidden="true">'+IC[st]+'</span>'+esc(l)+'</span>'}
  function clone(o){return JSON.parse(JSON.stringify(o))}
  var S=D.tuned?clone(D.tuned):{w:clone(D.orig.weights),t:clone(D.orig.thresholds),must:clone(D.orig.must)};
  var R={};
  function score(c){
    var tot=0,ws=0;D.dims.forEach(function(d){var v=c.dims[d.key],w=+S.w[d.key]||0;
      if(typeof v==='number'&&w){v=Math.max(1,Math.min(5,v));tot+=w*(v-1)/4;ws+=w}});
    var sc=ws?Math.floor(100*tot/ws+0.5):0;
    var musts=D.reqs.filter(function(r){return S.must[r.id]});
    var missed=musts.filter(function(r){return c.req[r.id]==='not_met'}),part=musts.filter(function(r){return c.req[r.id]==='partial'});
    var rec=!c.readable?'Unreadable':c.tier==='High risk'?'Verify first':(sc>=S.t.advance&&!missed.length)?'Advance':
      (sc>=S.t.consider&&missed.length<=1)?'Consider':'Pass';
    return {score:sc,rec:rec,met:musts.length-missed.length-part.length,partial:part.length,total:musts.length,
      missed:missed.map(function(r){return r.label})}}
  function mustsTxt(r){return r.met+'/'+r.total+(r.partial?' +'+r.partial+' partial':'')}
  function ranked(){return D.cands.slice().sort(function(a,b){var x=R[a.id],y=R[b.id];
    return (RK[x.rec]-RK[y.rec])||(y.score-x.score)||(a.order-b.order)})}
  var CIRC=2*3.14159*26;
  function apply(){
    D.cands.forEach(function(c){R[c.id]=score(c)});
    var order=ranked(),lb=document.querySelector('.lb tbody'),cards=document.getElementById('cards'),hm=document.querySelector('.heat tbody');
    order.forEach(function(c,i){var r=R[c.id],sel='[data-id="'+c.id+'"]';
      var tr=lb&&lb.querySelector('tr'+sel);
      if(tr){tr.dataset.rec=r.rec;tr.querySelector('.js-rank').textContent=i+1;tr.querySelector('.js-score').textContent=r.score;
        var sb=tr.querySelector('.sbar');sb.title='Fit '+r.score+'/100';sb.firstChild.style.width=r.score+'%';
        tr.querySelector('.js-musts').textContent=mustsTxt(r);tr.querySelector('.js-rec').innerHTML=chip(r.rec,RS[r.rec]);lb.appendChild(tr)}
      var cd=document.getElementById('c-'+c.id);
      if(cd){cd.dataset.rec=r.rec;cd.querySelector('.js-rank').textContent='#'+(i+1);cd.querySelector('.js-rec').innerHTML=chip(r.rec,RS[r.rec]);
        var rv=cd.querySelector('.ring-val');rv.setAttribute('stroke-dashoffset',(CIRC*(1-r.score/100)).toFixed(1));
        cd.querySelector('.ring text').textContent=r.score;cd.querySelector('.ring').setAttribute('aria-label','Fit score '+r.score);
        var m=cd.querySelector('.js-musts');if(m)m.textContent=mustsTxt(r);if(cards)cards.appendChild(cd)}
      var hr=hm&&hm.querySelector('tr'+sel);if(hr)hm.appendChild(hr)});
    document.querySelectorAll('[data-req]').forEach(function(el){if(el.matches('em,.mustlbl'))el.hidden=!S.must[el.dataset.req]});
    var cnt=function(x){return D.cands.filter(function(c){return R[c.id].rec===x}).length};
    var set=function(id,v){var e=document.getElementById(id);if(e)e.textContent=v};
    set('kpi-advance',cnt('Advance'));set('kpi-consider',cnt('Consider'));set('kpi-pass',cnt('Pass'));
    var sc=D.cands.filter(function(c){return R[c.id].rec!=='Unreadable'}).map(function(c){return R[c.id].score}).sort(function(a,b){return a-b});
    var med=!sc.length?0:sc.length%2?sc[(sc.length-1)/2]:Math.floor((sc[sc.length/2-1]+sc[sc.length/2])/2+0.5);set('kpi-median','median fit '+med);
    D.dims.forEach(function(d){set('w-'+d.key,S.w[d.key]);set('tv-'+d.key,S.w[d.key]);var i=document.getElementById('tw-'+d.key);if(i)i.value=S.w[d.key]});
    set('th-adv',S.t.advance);set('th-con',S.t.consider);
    var ta=document.getElementById('t-adv'),tc=document.getElementById('t-con');if(ta&&document.activeElement!==ta)ta.value=S.t.advance;if(tc&&document.activeElement!==tc)tc.value=S.t.consider;
    document.querySelectorAll('.mt').forEach(function(b){b.setAttribute('aria-pressed',S.must[b.dataset.req]?'true':'false')});
    // what changed
    var ch=[];D.dims.forEach(function(d){if(+S.w[d.key]!==+D.orig.weights[d.key])ch.push(d.label+' '+D.orig.weights[d.key]+' → '+S.w[d.key])});
    if(+S.t.advance!==+D.orig.thresholds.advance)ch.push('Advance at '+S.t.advance);
    if(+S.t.consider!==+D.orig.thresholds.consider)ch.push('Consider at '+S.t.consider);
    D.reqs.forEach(function(r){if(!!S.must[r.id]!==!!D.orig.must[r.id])ch.push(r.label+(S.must[r.id]?' now a must-have':' now nice-to-have'))});
    var note=document.getElementById('tune-note');if(note){note.hidden=!ch.length;set('tune-text','Adjusted view: '+ch.join('; ')+'. Scores and recommendations reflect these settings, not the original screen.')}
    filt();renderCmp()}
  document.querySelectorAll('#tune input[type=range]').forEach(function(i){i.addEventListener('input',function(){S.w[i.dataset.k]=+i.value;apply()})});
  [['t-adv','advance'],['t-con','consider']].forEach(function(p){var i=document.getElementById(p[0]);
    if(i)i.addEventListener('input',function(){var v=parseInt(i.value,10);if(!isNaN(v)){S.t[p[1]]=Math.max(0,Math.min(100,v));apply()}})});
  document.querySelectorAll('.mt').forEach(function(b){b.addEventListener('click',function(){S.must[b.dataset.req]=!S.must[b.dataset.req];apply()})});
  on('tune-reset',function(){S={w:clone(D.orig.weights),t:clone(D.orig.thresholds),must:clone(D.orig.must)};apply()});
  // ---------------------------------------------------------------- compare
  var picks=[];
  document.querySelectorAll('.cmp input').forEach(function(cb){cb.addEventListener('change',function(){
    if(cb.checked){picks.push(cb.value);if(picks.length>2){var old=picks.shift();var o=document.querySelector('.cmp input[value="'+old+'"]');if(o)o.checked=false}}
    else picks=picks.filter(function(x){return x!==cb.value});renderCmp()})});
  on('cmp-clear',function(){picks=[];document.querySelectorAll('.cmp input').forEach(function(c){c.checked=false});renderCmp()});
  function renderCmp(){var box=document.getElementById('compare');if(!box)return;box.hidden=picks.length!==2;if(picks.length!==2)return;
    var cs=picks.map(function(id){return D.cands.filter(function(c){return c.id===id})[0]});
    var row=function(l,f,best){var v=cs.map(f),b='';if(best){var n=cs.map(best);if(n[0]!==n[1])b=n[0]>n[1]?0:1}
      return '<tr><th scope="row">'+l+'</th>'+v.map(function(x,i){return '<td'+(i===b?' class="best"':'')+'>'+x+'</td>'}).join('')+'</tr>'};
    var ul=function(xs){return xs&&xs.length?'<ul>'+xs.map(function(x){return '<li>'+esc(x)+'</li>'}).join('')+'</ul>':'<span class="muted">none</span>'};
    var h='<table class="cmp-t"><thead><tr><th></th>'+cs.map(function(c){return '<th scope="col">'+esc(c.name)+'</th>'}).join('')+'</tr></thead><tbody>';
    h+=row('Fit score',function(c){return '<b>'+R[c.id].score+'</b>'},function(c){return R[c.id].score});
    h+=row('Recommendation',function(c){return chip(R[c.id].rec,RS[R[c.id].rec])});
    h+=row('Integrity',function(c){return chip(c.tier,TS[c.tier])});
    D.dims.forEach(function(d){h+=row(esc(d.label)+' <span class="muted small">w '+S.w[d.key]+'</span>',function(c){var v=c.dims[d.key];
      return v==null?'n/a':'<span class="mini"><span style="width:'+(v/5*100)+'%"></span></span>'+v+'/5'},function(c){return c.dims[d.key]||0})});
    h+=row('Must-haves',function(c){return mustsTxt(R[c.id])},function(c){return R[c.id].met});
    h+=row('Missed must-haves',function(c){return R[c.id].missed.length?esc(R[c.id].missed.join(', ')):'<span class="muted">none</span>'});
    h+=row('Top integrity flag',function(c){return c.top_flag?esc(c.top_flag):'<span class="muted">none</span>'});
    h+=row('Strengths',function(c){return ul(c.strengths)});h+=row('Gaps',function(c){return ul(c.gaps)});
    document.getElementById('cmp-body').innerHTML=h+'</tbody></table>'}
  // ---------------------------------------------------------------- exports reflect the current view
  function csvCell(v){var x=v==null?'':String(v);if(/^[=+\-@\t\r]/.test(x))x="'"+x;return /[",\n\r]/.test(x)?'"'+x.replace(/"/g,'""')+'"':x}
  function buildCSV(){var rows=[D.cols.join(',')];ranked().forEach(function(c,i){var r=R[c.id];
    var v={rank:i+1,name:c.name,fit_score:r.score,recommendation:r.rec,integrity:c.tier,must_haves_met:r.met,must_haves_partial:r.partial,
      must_haves_total:r.total,missed_must_haves:r.missed.join('; '),top_integrity_flag:c.top_flag,headline:c.headline,source_file:c.file};
    D.dims.forEach(function(d){v[d.key]=c.dims[d.key]});rows.push(D.cols.map(function(k){return csvCell(v[k])}).join(','))});return rows.join('\n')+'\n'}
  on('dl-html',function(){var c=root.cloneNode(true);c.removeAttribute('data-theme');
    c.querySelectorAll('.hidden-row').forEach(function(el){el.classList.remove('hidden-row')});
    var dd=clone(D);dd.tuned=S;c.querySelector('#cs-data').textContent=JSON.stringify(dd).replace(/</g,'\\u003c');
    dl(D.base+'.html','text/html','<!doctype html>\n'+c.outerHTML)});
  on('dl-csv',function(){dl(D.base+'.csv','text/csv','﻿'+buildCSV())});
  apply();
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


def report_data(signals, req, cands, weights, thresholds, reqs):
    """Everything the report needs to rescore itself live in the browser."""
    order = {s["id"]: i for i, s in enumerate(signals["candidates"])}
    return {
        "base": report_basename(req, signals),
        "weights": weights, "thresholds": thresholds,
        "orig": {"weights": weights, "thresholds": thresholds, "must": {r["id"]: bool(r.get("must")) for r in reqs}},
        "reqs": [{"id": r["id"], "label": r["label"], "must": bool(r.get("must"))} for r in reqs],
        "dims": [{"key": k, "label": l} for k, l, _ in DIMENSIONS],
        "cols": CSV_COLS,
        "cands": [{"id": c["id"], "name": c["name"], "headline": c["headline"], "order": order.get(c["id"], 0),
                   "readable": c["sig"].get("readable", True), "tier": c["tier"],
                   "dims": {d["key"]: d["used"] for d in c["dims"]},
                   "req": {rid: v["status"] for rid, v in c["req_status"].items()},
                   "top_flag": next((f.get("title") for f in c["flags"] if f.get("severity") in ("strong", "moderate")), ""),
                   "strengths": c["strengths"], "gaps": c["gaps"],
                   "file": Path(c["sig"].get("file", "")).name} for c in cands],
    }


def tune_panel(reqs, weights, thresholds):
    sliders = "".join(
        f'<div class="tw"><label for="tw-{k}">{esc(l)}<output id="tv-{k}">{weights.get(k, 0)}</output></label>'
        f'<input type="range" id="tw-{k}" min="0" max="50" step="5" data-k="{k}" value="{weights.get(k, 0)}"></div>'
        for k, l, _ in DIMENSIONS)
    toggles = "".join(
        f'<button type="button" class="mt" data-req="{esc(r["id"])}" aria-pressed="{"true" if r.get("must") else "false"}">'
        f'{esc(r["label"])}</button>' for r in reqs)
    return f'''<details class="panel tune" id="tune" open>
  <summary><b>Tune the ranking</b><span class="muted small">Change the weights, thresholds, or must-haves. Scores, recommendations, and order update instantly. Integrity ratings never change.</span></summary>
  <div class="tune-grid">
    <div><h4>Weights</h4><div class="sliders">{sliders}</div></div>
    <div><h4>Must-haves <span class="muted small">(click to toggle)</span></h4><div class="mtoggles">{toggles}</div>
      <h4>Thresholds</h4><div class="thr"><label>Advance at <input type="number" id="t-adv" min="0" max="100" value="{thresholds["advance"]}"></label>
      <label>Consider at <input type="number" id="t-con" min="0" max="100" value="{thresholds["consider"]}"></label></div></div>
  </div>
</details>
<div class="tune-note" id="tune-note" hidden><span id="tune-text"></span><button type="button" id="tune-reset">Reset to original</button></div>'''


def bar(score, width=10):
    n = max(0, min(width, int(score / 100 * width + 0.5)))
    return "\u2588" * n + "\u2591" * (width - n)


SHORT_DIM = {"must_have": "must", "experience": "experience", "impact": "impact", "learning_agility": "learning",
             "work_style": "work style", "nice_to_have": "nice"}


def _title(req):
    return f"{req.get('role', 'Role')}{', ' + req['company'] if req.get('company') else ''}"


def welcome_md(posting=None, apps=0):
    """Chat card for Step 1: what the skill does and a checklist of what it still needs."""
    box = lambda done: "[x]" if done else "[ ]"
    lines = ["### Candidate Screen",
             "Screens a stack of applications against a job posting: fit and learning agility scored with evidence, "
             "fake and AI-gamed applications flagged, and a ranked report you can retune.", "",
             "**Step 1 of 4 \u00b7 Send me**",
             f"- {box(posting)} **Job posting:** a link, a file, or pasted text" + (f" (got: {posting})" if posting else ""),
             f"- {box(apps)} **Applications:** attach the resumes (.pdf, .docx, .txt, .md, .html)" +
             (f" (got {apps})" if apps else ""),
             "- [ ] *Optional:* say `web checks ok` to let me look up employers for flagged candidates, and name any "
             "legal requirement for the role (for example work authorization)", "",
             "**Then:** 2 \u00b7 you approve the requirements \u2192 3 \u00b7 I scan and score \u2192 4 \u00b7 ranked results and report", "",
             'Try: *"Screen these resumes against the attached posting."*']
    return "\n".join(lines)


def requirements_md(req, page=None):
    """Chat card for Step 2: the drafted requirements, weights, and how to reply."""
    reqs = req.get("requirements", [])
    musts = sum(1 for r in reqs if r.get("must"))
    lines = ["### Step 2 of 4 \u00b7 Review requirements",
             f"**{_title(req)}** \u00b7 {musts} must-have{'s' if musts != 1 else ''} \u00b7 {len(reqs) - musts} nice-to-have", "",
             "| ID | | Requirement | Matches on |", "|---|---|---|---|"]
    for r in sorted(reqs, key=lambda r: not r.get("must")):
        lines.append(f"| {r['id']} | {'**MUST**' if r.get('must') else 'nice'} | {r['label']} | {', '.join(r.get('terms', [])[:6])} |")
    w = {**DEFAULT_WEIGHTS, **req.get("weights", {})}
    th = {**DEFAULT_THRESHOLDS, **req.get("thresholds", {})}
    lines += ["", "**Weights** " + " \u00b7 ".join(f"{l} {w.get(k, 0)}" for k, l, _ in DIMENSIONS),
              f"**Advance at** {th['advance']} \u00b7 **Consider at** {th['consider']}"]
    if req.get("notes"):
        lines += [""] + [f"> {n}" for n in req["notes"]]
    lines += ["", "**Your move**"]
    if page:
        lines.append(f"- Open **{Path(page).name}** to adjust with toggles and sliders, then paste the reply it gives you")
    lines += ["- Or reply in words: `R5 nice` \u00b7 `R7 must` \u00b7 `remove R10` \u00b7 `add Okta admin, must` \u00b7 `learning 25` \u00b7 `advance 70`",
              "- Or: `looks good`"]
    return "\n".join(lines)


def scan_md(signals, req):
    """Chat card for Step 3: what the scan found, before any scoring."""
    cands = signals.get("candidates", [])
    n_req = len(req.get("requirements", []))
    lines = ["### Step 3 of 4 \u00b7 Screening",
             f"Read {len(cands)} application{'s' if len(cands) != 1 else ''}. Scoring each against the rubric next.", "",
             "| Applicant | File | Years | Shown in a role | Integrity scan |", "|---|---|---|---|---|"]
    for c in cands:
        sev = [f.get("severity") for f in c.get("flags", [])]
        top = next((f["title"] for f in c.get("flags", []) if f.get("severity") == "strong"), "") or \
            next((f["title"] for f in c.get("flags", []) if f.get("severity") == "moderate"), "")
        integ = ("**High risk** \u00b7 " + top if sev.count("strong") or sev.count("moderate") >= 3 else
                 "Verify \u00b7 " + top if sev.count("moderate") or sev.count("weak") >= 3 else "Clear")
        dem = sum(1 for v in (c.get("coverage") or {}).values() if v.get("status") == "demonstrated")
        name = (c.get("contacts") or {}).get("name_guess") or c["id"]
        lines.append(f"| {name} | {Path(c.get('file', '')).name} | {(c.get('timeline') or {}).get('years_total', 'n/a')} | "
                     f"{dem}/{n_req} | {integ if c.get('readable', True) else 'Unreadable file'} |")
    return "\n".join(lines)


def summary_md(signals, evals, req, files=None):
    """Chat card for Step 4: ranked table with score bars, integrity callouts, files, and suggested next replies."""
    cands = compute(signals, evals, req)[0]
    count = lambda r: sum(1 for c in cands if c["rec"] == r)
    lines = ["### Step 4 of 4 \u00b7 Results",
             f"**{_title(req)}** \u00b7 {len(cands)} application{'s' if len(cands) != 1 else ''}",
             f"Advance **{count('Advance')}** \u00b7 Consider **{count('Consider')}** \u00b7 Verify first **{count('Verify first')}**"
             f" \u00b7 Pass **{count('Pass')}**" + (f" \u00b7 Unreadable **{count('Unreadable')}**" if count("Unreadable") else ""), "",
             "| # | Candidate | Fit | Recommendation | Integrity | Must-haves | Learning |", "|---|---|---|---|---|---|---|"]
    for i, c in enumerate(cands, 1):
        la = next((d["used"] for d in c["dims"] if d["key"] == "learning_agility"), None)
        lines.append(f"| {i} | **{c['name']}** | `{bar(c['score'])}` {c['score']} | {c['rec']} | {c['tier']} | "
                     f"{musts_cell(c)} | {la if la is not None else 'n/a'}/5 |")
    lines.append("")
    for c in cands:
        lines.append(f"- **{c['name']}:** {c['headline']}" + (f" Missed: {', '.join(c['missed'])}." if c["missed"] else ""))
    flagged = [c for c in cands if c["tier"] != "Clear"]
    if flagged:
        lines += ["", "**Integrity**"]
        for c in flagged:
            top = [f for f in c["flags"] if f.get("severity") in ("strong", "moderate")][:3]
            lines.append(f"- **{c['name']} ({c['tier']}):** " + "; ".join(f.get("title", "") for f in top) + ".")
            nxt = ("Verify identity, contact details, and employers before any interview." if c["tier"] == "High risk"
                   else (top[0].get("verify", "") if top else ""))
            if nxt:
                lines.append(f"  Next step: {nxt}")
    unv = sum(c["unverified_quotes"] for c in cands)
    if unv:
        lines += ["", f"{unv} evidence quote(s) could not be found in the application text and were not counted."]
    if files:
        lines += ["", "**Files**"] + [f"- {k}: `{v}`" for k, v in files.items()]
        lines.append("The HTML report retunes live (weights, thresholds, must-haves) and compares any two candidates.")
    a, b = (cands[0]["name"].split()[0], cands[1]["name"].split()[0]) if len(cands) > 1 else ("1", "2")
    flag_name = flagged[0]["name"].split()[0] if flagged else None
    lines += ["", "**Next** \u00b7 reply with " + " \u00b7 ".join(
        [f"`compare {a} and {b}`", "`learning 25`", "`R5 nice`"] + ([f"`{flag_name}'s flags`"] if flag_name else [])
        + ["`questions for " + a + "`", "`pdf`"])]
    return "\n".join(lines)


# --------------------------------------------------------------------------- requirement changes (chat mode)

CHANGES_HEADER = "Requirement changes (Candidate Screen)"


def _dim_key(word):
    word = word.strip().lower().replace("-", " ").replace("_", " ")
    for k, short in SHORT_DIM.items():
        if word in (short, k.replace("_", " "), dict((kk, l.lower()) for kk, l, _ in DIMENSIONS)[k]):
            return k
    return None


def apply_changes(req, text):
    """Apply a changes block (from the review page, or written by Claude from a chat reply). Returns (req, changes)."""
    req = json.loads(json.dumps(req))
    reqs = req.setdefault("requirements", [])
    ids = {r["id"]: r for r in reqs}
    next_id = 1 + max([int(m.group(1)) for r in reqs for m in [re.match(r"R(\d+)$", r["id"])] if m] or [0])
    done, errors = [], []
    t = text.strip()
    if re.fullmatch(r"(?i)looks? good\.?|lgtm|approve[d]?|no changes", t):
        return req, ["no changes"]
    for raw in t.splitlines():
        line = raw.strip().lstrip("-* ").strip()
        if not line or line.startswith(CHANGES_HEADER) or ":" not in line:
            continue
        key, val = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "must":
            want = {x.strip().upper() for x in re.split(r"[,\s]+", val) if x.strip()}
            bad = want - set(ids)
            if bad:
                errors.append(f"unknown requirement id(s): {', '.join(sorted(bad))}")
            for r in reqs:
                if bool(r.get("must")) != (r["id"] in want):
                    r["must"] = r["id"] in want
                    done.append(f"{r['id']} {r['label']}: {'must-have' if r['must'] else 'nice-to-have'}")
        elif key == "remove":
            for x in re.split(r"[,\s]+", val):
                x = x.strip().upper()
                if x in ids:
                    reqs.remove(ids.pop(x))
                    done.append(f"removed {x}")
                elif x:
                    errors.append(f"cannot remove unknown id {x}")
        elif key == "add":
            parts = [x.strip() for x in val.split("|")]
            if not parts[0]:
                errors.append("add needs a label")
                continue
            must = len(parts) > 1 and parts[1].lower().startswith("must")
            terms = [x.strip() for x in parts[2].split(",") if x.strip()] if len(parts) > 2 else []
            r = {"id": f"R{next_id}", "label": parts[0], "terms": terms, "must": must, "text": parts[0]}
            next_id += 1
            reqs.append(r)
            ids[r["id"]] = r
            done.append(f"added {r['id']} {r['label']} ({'must-have' if must else 'nice-to-have'})")
        elif key == "weights":
            w = req.setdefault("weights", dict(DEFAULT_WEIGHTS))
            for m in re.finditer(r"([A-Za-z_ -]+?)\s*[=:]?\s*(\d+)", val):
                k = _dim_key(m.group(1))
                if k is None:
                    errors.append(f"unknown weight {m.group(1).strip()}")
                elif w.get(k) != int(m.group(2)):
                    done.append(f"{dict((kk, l) for kk, l, _ in DIMENSIONS)[k]} {w.get(k, DEFAULT_WEIGHTS[k])} \u2192 {m.group(2)}")
                    w[k] = int(m.group(2))
        elif key == "thresholds":
            th = req.setdefault("thresholds", dict(DEFAULT_THRESHOLDS))
            for m in re.finditer(r"(advance|consider)\s*[=:]?\s*(\d+)", val, re.I):
                k = m.group(1).lower()
                if th.get(k) != int(m.group(2)):
                    done.append(f"{k.title()} at {m.group(2)}")
                    th[k] = max(0, min(100, int(m.group(2))))
        else:
            errors.append(f"unknown line: {raw.strip()}")
    if errors:
        raise ValueError("; ".join(errors))
    return req, done or ["no changes"]


REVIEW_JS = r"""
(function(){
var D=JSON.parse(document.getElementById('rv-data').textContent);
var S={must:{},removed:{},added:[],w:Object.assign({},D.weights),t:Object.assign({},D.thresholds)};
D.reqs.forEach(function(r){S.must[r.id]=!!r.must});
function esc(x){return String(x==null?'':x).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function rows(){var h='';D.reqs.forEach(function(r){var rm=S.removed[r.id];
  h+='<tr class="'+(rm?'rm':'')+'"><td class="id">'+esc(r.id)+'</td><td><button type="button" class="mt" data-id="'+esc(r.id)+'" aria-pressed="'+(S.must[r.id]?'true':'false')+'"'+(rm?' disabled':'')+'>'+(S.must[r.id]?'MUST':'nice')+'</button></td>'+
  '<td><b>'+esc(r.label)+'</b><div class="terms">'+esc((r.terms||[]).join(', '))+'</div></td>'+
  '<td><button type="button" class="x" data-rm="'+esc(r.id)+'" title="'+(rm?'Restore':'Remove')+'">'+(rm?'Restore':'Remove')+'</button></td></tr>'});
  S.added.forEach(function(a,i){h+='<tr class="new"><td class="id">new</td><td><button type="button" class="mt" data-add="'+i+'" aria-pressed="'+(a.must?'true':'false')+'">'+(a.must?'MUST':'nice')+'</button></td>'+
  '<td><b>'+esc(a.label)+'</b><div class="terms">'+esc(a.terms)+'</div></td><td><button type="button" class="x" data-rmadd="'+i+'">Remove</button></td></tr>'});
  document.getElementById('rv-rows').innerHTML=h;
  document.querySelectorAll('.mt[data-id]').forEach(function(b){b.onclick=function(){S.must[b.dataset.id]=!S.must[b.dataset.id];upd()}});
  document.querySelectorAll('.mt[data-add]').forEach(function(b){b.onclick=function(){var a=S.added[+b.dataset.add];a.must=!a.must;upd()}});
  document.querySelectorAll('[data-rm]').forEach(function(b){b.onclick=function(){S.removed[b.dataset.rm]=!S.removed[b.dataset.rm];upd()}});
  document.querySelectorAll('[data-rmadd]').forEach(function(b){b.onclick=function(){S.added.splice(+b.dataset.rmadd,1);upd()}})}
function out(){var L=[],mustNow=D.reqs.filter(function(r){return !S.removed[r.id]&&S.must[r.id]}).map(function(r){return r.id});
  var mustOrig=D.reqs.filter(function(r){return !S.removed[r.id]&&r.must}).map(function(r){return r.id});
  if(mustNow.join()!==mustOrig.join())L.push('must: '+mustNow.join(', '));
  var rm=Object.keys(S.removed).filter(function(k){return S.removed[k]});if(rm.length)L.push('remove: '+rm.join(', '));
  S.added.forEach(function(a){L.push('add: '+a.label.replace(/[|\n]/g,' ')+' | '+(a.must?'must':'nice')+' | '+a.terms.replace(/[|\n]/g,' '))});
  var wc=D.dims.filter(function(d){return +S.w[d.key]!==+D.weights[d.key]});
  if(wc.length)L.push('weights: '+D.dims.map(function(d){return d.short+' '+S.w[d.key]}).join(', '));
  if(+S.t.advance!==+D.thresholds.advance||+S.t.consider!==+D.thresholds.consider)L.push('thresholds: advance '+S.t.advance+', consider '+S.t.consider);
  return L.length?D.header+'\n'+L.join('\n'):'looks good'}
function upd(){rows();D.dims.forEach(function(d){document.getElementById('v-'+d.key).textContent=S.w[d.key]});
  var o=out();document.getElementById('rv-out').value=o;var n=o==='looks good'?0:o.split('\n').length-1;
  document.getElementById('rv-count').textContent=n?n+' change'+(n>1?'s':''):'No changes yet';
  document.getElementById('rv-copy').textContent=n?'Copy my changes':'Copy "looks good"';
  var musts=D.reqs.filter(function(r){return !S.removed[r.id]&&S.must[r.id]}).length+S.added.filter(function(a){return a.must}).length;
  document.getElementById('rv-musts').textContent=musts+' must-have'+(musts===1?'':'s')}
document.querySelectorAll('input[type=range]').forEach(function(i){i.oninput=function(){S.w[i.dataset.k]=+i.value;upd()}});
['advance','consider'].forEach(function(k){var i=document.getElementById('t-'+k);i.oninput=function(){var v=parseInt(i.value,10);if(!isNaN(v)){S.t[k]=Math.max(0,Math.min(100,v));upd()}}});
document.getElementById('rv-add').onclick=function(){var l=document.getElementById('a-label'),t=document.getElementById('a-terms'),m=document.getElementById('a-must');
  if(!l.value.trim()){l.focus();return}S.added.push({label:l.value.trim(),terms:t.value.trim(),must:m.checked});l.value='';t.value='';m.checked=false;upd()};
document.getElementById('rv-copy').onclick=function(){var ta=document.getElementById('rv-out'),msg=document.getElementById('rv-msg');
  function ok(){msg.textContent='Copied. Paste it into the chat to continue.';msg.className='ok'}
  function manual(){ta.focus();ta.select();msg.textContent='Selected. Press Cmd+C (or Ctrl+C), then paste it into the chat.';msg.className='warn'}
  try{if(navigator.clipboard&&window.isSecureContext){navigator.clipboard.writeText(ta.value).then(ok,function(){manual();try{document.execCommand('copy')&&ok()}catch(e){}})}
  else{manual();if(document.execCommand('copy'))ok()}}catch(e){manual()}};
upd();
})();
"""


def review_page(req):
    """Standalone Step 2 page: toggle must-haves, add or remove requirements, set weights; copy a reply for the chat."""
    reqs = req.get("requirements", [])
    w = {**DEFAULT_WEIGHTS, **req.get("weights", {})}
    th = {**DEFAULT_THRESHOLDS, **req.get("thresholds", {})}
    data = {"reqs": [{"id": r["id"], "label": r["label"], "terms": r.get("terms", [])[:8], "must": bool(r.get("must"))} for r in reqs],
            "weights": w, "thresholds": th, "header": CHANGES_HEADER,
            "dims": [{"key": k, "label": l, "short": SHORT_DIM[k]} for k, l, _ in DIMENSIONS]}
    sliders = "".join(f'<div class="tw"><label for="w-{k}">{esc(l)}<output id="v-{k}">{w[k]}</output></label>'
                      f'<input type="range" id="w-{k}" data-k="{k}" min="0" max="50" step="5" value="{w[k]}"></div>'
                      for k, l, _ in DIMENSIONS)
    notes = "".join(f"<li>{esc(n)}</li>" for n in req.get("notes", []))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Review requirements</title><style>{CSS}
.rv{{max-width:980px}}.steps{{display:flex;gap:6px;flex-wrap:wrap;margin-top:14px;padding:0;list-style:none}}
.steps li{{font-size:12px;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,.14);color:rgba(255,255,255,.8)}}.steps li.on{{background:#fff;color:#0d366b;font-weight:700}}
.rvt{{width:100%}}.rvt td{{padding:9px 8px;vertical-align:middle}}.rvt .id{{color:var(--muted);font-size:12px;width:40px}}
.rvt .terms{{font-size:12px;color:var(--muted);margin-top:2px}}.rvt tr.rm b,.rvt tr.rm .terms{{text-decoration:line-through;opacity:.5}}
.rvt tr.new{{background:color-mix(in srgb,var(--series) 8%,transparent)}}
.rvt .mt{{min-width:62px}}.rvt .mt[aria-pressed="true"]:before{{content:""}}
.x{{font:inherit;font-size:12px;border:1px solid var(--border);background:var(--surface);color:var(--ink-2);border-radius:999px;padding:3px 10px;cursor:pointer}}
.addrow{{display:grid;grid-template-columns:1.2fr 1.6fr auto auto;gap:8px;align-items:center;margin-top:10px}}
.addrow input[type=text]{{font:inherit;padding:7px 10px;border:1px solid var(--border);border-radius:8px;background:var(--page);color:var(--ink)}}
@media(max-width:700px){{.addrow{{grid-template-columns:1fr}}}}
.reply{{position:sticky;bottom:0;background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px;margin-top:16px;box-shadow:0 -6px 24px rgba(0,0,0,.12)}}
.reply textarea{{width:100%;min-height:86px;font:12px/1.5 ui-monospace,Menlo,monospace;padding:8px;border:1px solid var(--border);border-radius:8px;background:var(--page);color:var(--ink);resize:vertical}}
.reply .rbar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:8px}}
.big{{font:inherit;font-weight:700;background:var(--series);color:#fff;border:0;border-radius:10px;padding:9px 16px;cursor:pointer}}
#rv-msg.ok{{color:var(--good-ink)}}#rv-msg.warn{{color:var(--warn-ink)}}
</style></head><body>
<header class="hero" style="padding:28px 0 64px"><div class="wrap rv">
  <p class="eyebrow">Candidate screen \u00b7 step 2 of 4</p><h1>Review requirements</h1>
  <p>{esc(_title(req))}. Toggle must-haves, remove or add requirements, and set the weights. Then copy your reply into the chat.</p>
  <ol class="steps"><li>1 \u00b7 Posting and resumes</li><li class="on">2 \u00b7 Requirements</li><li>3 \u00b7 Screening</li><li>4 \u00b7 Results</li></ol>
</div></header>
<main class="wrap rv">
  <div class="panel" style="margin-top:-40px">
    {f'<div class="notes" style="margin-bottom:10px"><b>Notes from Claude</b><ul class="small">{notes}</ul></div>' if notes else ''}
    <h4>Requirements <span class="muted small" id="rv-musts"></span></h4>
    <table class="rvt"><tbody id="rv-rows"></tbody></table>
    <div class="addrow"><input type="text" id="a-label" placeholder="Add a requirement, e.g. Okta administration">
      <input type="text" id="a-terms" placeholder="Words to match, comma separated (optional)">
      <label class="small"><input type="checkbox" id="a-must"> must-have</label><button type="button" class="x" id="rv-add">Add</button></div>
  </div>
  <div class="panel" style="margin-top:14px"><h4>Weights</h4><div class="sliders">{sliders}</div>
    <h4>Thresholds</h4><div class="thr"><label>Advance at <input type="number" id="t-advance" min="0" max="100" value="{th["advance"]}"></label>
    <label>Consider at <input type="number" id="t-consider" min="0" max="100" value="{th["consider"]}"></label></div>
    <p class="small muted">Weights are normalized, so they do not need to add up to 100. Integrity is rated separately and never weighted.</p></div>
  <div class="reply"><div class="rbar"><b>Your reply</b><span class="muted small" id="rv-count"></span>
    <button type="button" class="big" id="rv-copy" style="margin-left:auto">Copy my changes</button></div>
    <textarea id="rv-out" readonly aria-label="Reply to paste into the chat"></textarea><p id="rv-msg" class="small"></p></div>
</main>
<script type="application/json" id="rv-data">{json.dumps(data).replace("<", "\\u003c")}</script>
<script>{REVIEW_JS}</script>
</body></html>'''


def render(signals, evals, req, title=None):
    cands, reqs, weights, thresholds, ev_by = compute(signals, evals, req)
    n = len(cands)
    count = lambda r: sum(1 for c in cands if c["rec"] == r)
    flagged = sum(1 for c in cands if c["tier"] != "Clear")
    scores = [c["score"] for c in cands if c["rec"] != "Unreadable"]
    med = int(statistics.median(scores) + 0.5) if scores else 0
    missing_evals = [s["id"] for s in signals["candidates"] if s["id"] not in ev_by]
    role = req.get("role", "Role")
    company = req.get("company", "")
    title = title or f"{role} candidate screen"
    musts = sum(1 for r in reqs if r.get("must"))

    kpis = [("Applications", n, "", f"median fit {med}"), ("Advance", count("Advance"), "k-good", "score and must-haves clear"),
            ("Consider", count("Consider"), "k-warn", "worth a closer look"), ("Pass", count("Pass"), "", "below bar for this role"),
            ("Integrity flags", flagged, "k-crit", f'{count("Verify first")} need identity checks first')]
    kpi_ids = ["kpi-n", "kpi-advance", "kpi-consider", "kpi-pass", "kpi-flags"]
    kpi_html = "".join(f'<div class="kpi {cls}"><span>{esc(k)}</span><b id="{kid}">{v}</b><i{" id=kpi-median" if kid == "kpi-n" else ""}>'
                       f'{esc(sub)}</i></div>' for kid, (k, v, cls, sub) in zip(kpi_ids, kpis))
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
    cards = '<div id="cards">' + "".join(card(c, i, reqs, i <= 3) for i, c in enumerate(cands, 1)) + "</div>"
    wrows = "".join(f'<tr><td>{esc(l)}</td><td class="num" id="w-{k}">{weights.get(k, 0)}</td><td class="muted">{esc(d)}</td></tr>'
                    for k, l, d in DIMENSIONS)
    src = "".join(f'<li><a href="{esc(u)}" rel="noopener noreferrer" target="_blank">{esc(t)}</a></li>' for t, u in SOURCES)
    data = json.dumps(report_data(signals, req, cands, weights, thresholds, reqs)).replace("<", "\\u003c")

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
  <h2>Shortlist</h2><p class="sub">Ranked by recommendation, then fit score. Learning agility is shown on its own because it predicts ramp-up on what they do not know yet. <span class="screen-only">Tune the ranking below to see how it shifts.</span></p>
  {tune_panel(reqs, weights, thresholds)}
  {filters}{leaderboard(cands)}
  <div class="panel compare" id="compare" hidden><div class="cmp-head"><b>Side by side</b><span class="muted small">Tick Compare on any two rows.</span><button type="button" id="cmp-clear">Clear</button></div><div id="cmp-body"></div></div>
  <h2>Requirement coverage</h2><p class="sub">Met means the skill shows up inside a dated role, not just a skills list.</p>
  {heatmap(cands, reqs)}
  <h2>Candidates</h2><p class="sub">Every score carries a rationale and quotes. A check mark means the quote was found in the application; a question mark means it was not.</p>
  {cards}
  <h2>How this was scored</h2>
  <div class="method">
    <div class="panel"><h4>Fit score weights</h4><table class="weights"><tbody>{wrows}</tbody></table>
      <p class="small muted">Each dimension is scored 1 to 5 with anchors from the rubric, then weighted to 0-100. Advance at <span id="th-adv">{thresholds["advance"]}</span>+ with no must-have missed; Consider at <span id="th-con">{thresholds["consider"]}</span>+ with at most one missed. A 4 or 5 with no verifiable quote counts as 3.</p></div>
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
    md = summary_md(sig, ev, req)
    check("| 1 | **A** |" in md and "\u2588" in md and "Verify first" in md, "chat summary ranks with score bars")
    check("| R1 | **MUST** | Kubernetes |" in requirements_md(req), "chat requirements card lists must-haves")
    req2 = {"role": "T", "requirements": [{"id": "R1", "label": "K8s", "must": True}, {"id": "R2", "label": "Go", "must": False}]}
    new, done = apply_changes(req2, CHANGES_HEADER + "\nmust: R2\nremove: R1\nadd: Okta admin | must | Okta, SSO\n"
                              "weights: must 30, experience 25, impact 15, learning 25, work style 5, nice 10\nthresholds: advance 65, consider 55")
    got = {r["id"]: r["must"] for r in new["requirements"]}
    check(got == {"R2": True, "R3": True} and new["weights"]["learning_agility"] == 25 and new["thresholds"]["advance"] == 65,
          "apply-changes: must, remove, add, weights, thresholds")
    check(apply_changes(req2, "looks good")[1] == ["no changes"], "apply-changes: looks good is a no-op")
    try:
        apply_changes(req2, "must: R9")
        check(False, "apply-changes rejects unknown ids")
    except ValueError:
        check(True, "apply-changes rejects unknown ids")
    page = review_page(req2)
    check('id="rv-copy"' in page and "</script><script>" not in page.split('id="rv-data">')[1].split("</script>")[0] + "x",
          "review page renders with a safe data block")
    check("Step 1 of 4" in welcome_md() and "[x]" in welcome_md("posting.pdf", 3), "welcome card checklist")
    check('id="tune"' in out and '"orig"' in out, "report carries the live tuning panel and its data")
    print("all passed" if ok else "FAILURES")
    return 0 if ok else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "welcome":
        w = argparse.ArgumentParser(prog="render_report.py welcome")
        w.add_argument("--posting", help="short name of the posting already received")
        w.add_argument("--apps", type=int, default=0, help="number of applications already received")
        o = w.parse_args(sys.argv[2:])
        print(welcome_md(o.posting, o.apps))
        return
    if cmd == "requirements-md":
        r = argparse.ArgumentParser(prog="render_report.py requirements-md")
        r.add_argument("requirements")
        r.add_argument("--page", help="also write the interactive review page here")
        o = r.parse_args(sys.argv[2:])
        req = json.loads(Path(o.requirements).read_text())
        if o.page:
            Path(o.page).write_text(review_page(req))
        print(requirements_md(req, o.page))
        return
    if cmd == "apply-changes":
        r = argparse.ArgumentParser(prog="render_report.py apply-changes")
        r.add_argument("requirements")
        r.add_argument("changes", help="file with the reply, or - for stdin")
        o = r.parse_args(sys.argv[2:])
        text = sys.stdin.read() if o.changes == "-" else Path(o.changes).read_text()
        try:
            new, done = apply_changes(json.loads(Path(o.requirements).read_text()), text)
        except ValueError as e:
            sys.exit(f"not applied: {e}")
        Path(o.requirements).write_text(json.dumps(new, indent=2) + "\n")
        print("applied: " + "; ".join(done))
        return
    if cmd == "scan-md":
        print(scan_md(json.loads(Path(sys.argv[2]).read_text()), json.loads(Path(sys.argv[3]).read_text())))
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--signals", required=True)
    ap.add_argument("--evals", required=True)
    ap.add_argument("--requirements", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title")
    ap.add_argument("--json", help="also write the computed scores here")
    ap.add_argument("--csv", help="also write the shortlist as CSV here")
    ap.add_argument("--pdf", help="also print the report to PDF here (needs Chrome, Chromium, Edge, or Brave)")
    ap.add_argument("--markdown", help="also write a chat-ready results summary (ranked table with score bars) here")
    a = ap.parse_args()
    signals = json.loads(Path(a.signals).read_text())
    evals = json.loads(Path(a.evals).read_text())
    req = json.loads(Path(a.requirements).read_text())
    Path(a.out).write_text(render(signals, evals, req, a.title))
    print(f"report -> {a.out}")
    if a.csv:
        Path(a.csv).write_text("\ufeff" + to_csv(csv_rows(compute(signals, evals, req)[0])))
        print(f"csv -> {a.csv}")
    pdf_ok = False
    if a.pdf:
        pdf_ok, msg = make_pdf(a.out, a.pdf)
        print(f"pdf -> {msg}" if pdf_ok else msg)
    if a.markdown:
        files = {"Report (interactive)": str(Path(a.out).resolve())}
        if pdf_ok:
            files["PDF"] = str(Path(a.pdf).resolve())
        if a.csv:
            files["Shortlist CSV"] = str(Path(a.csv).resolve())
        Path(a.markdown).write_text(summary_md(signals, evals, req, files) + "\n")
        print(f"markdown -> {a.markdown}")
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
