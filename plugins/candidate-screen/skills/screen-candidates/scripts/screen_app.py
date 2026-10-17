#!/usr/bin/env python3
"""screen_app: local browser GUI for the screen-candidates skill.

The GUI and Claude talk through files in the workspace folder. The GUI collects the posting, the
applications, and the options, shows Claude's draft requirements for editing, then shows live
progress and the finished report. Claude does the reading and judgment in between.

Commands (stdlib only, Python 3.9+):

  serve    --workspace W [--apps PATH] [--port N] [--no-open]
           Start the GUI on 127.0.0.1 and open it in the browser. Runs until killed or idle 2 hours.
  wait     --workspace W --stage S1[,S2...] [--timeout SECONDS]
           Block until the GUI reaches one of the stages, then print the state as JSON.
  stage    --workspace W --stage S [--message TEXT] [--report FILE]
           Move the GUI to a stage (Claude calls this as work progresses).
  progress --workspace W --candidate ID --status queued|scoring|done [--name NAME]
           Update one candidate's progress card.
  selftest

Stages: intake -> intake_submitted -> drafting -> requirements_review -> approved -> scanning ->
        evaluating -> rendering -> done   (error at any point)

Security: binds 127.0.0.1 only; every request needs the random token in the URL; uploads are
size-limited and saved under the workspace with sanitized names. Nothing leaves the machine.
"""
import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_report as rr  # noqa: E402

APP_EXT = {".txt", ".md", ".html", ".htm", ".docx", ".pdf"}
MAX_UPLOAD = 25 * 1024 * 1024
IDLE_LIMIT = 2 * 3600
STAGES = ["intake", "intake_submitted", "drafting", "requirements_review", "approved", "scanning",
          "evaluating", "rendering", "done", "error"]

# --------------------------------------------------------------------------- state files


def app_dir(ws):
    d = Path(ws).expanduser().resolve() / "_app"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path, data):
    tmp = Path(str(path) + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def load_state(ws):
    return read_json(app_dir(ws) / "state.json", {"stage": "intake", "candidates": {}})


def save_state(ws, **changes):
    st = load_state(ws)
    st.update(changes)
    st["updated"] = datetime.now().isoformat(timespec="seconds")
    write_json(app_dir(ws) / "state.json", st)
    return st


def count_apps(path):
    p = Path(path).expanduser()
    if p.is_file():
        return 1 if p.suffix.lower() in APP_EXT else 0
    if not p.is_dir():
        return -1
    return sum(1 for f in p.rglob("*") if f.is_file() and f.suffix.lower() in APP_EXT
               and not any(part.startswith(("_", ".")) for part in f.relative_to(p).parts))


def safe_name(name):
    base = Path(name.replace("\\", "/")).name
    base = re.sub(r"[^A-Za-z0-9._ -]+", "_", base).strip(" .") or "file"
    return base[:120]


def scan_summary(ws):
    sig = read_json(Path(ws) / "signals.json")
    if not sig:
        return None
    out = []
    for c in sig.get("candidates", []):
        sev = [f.get("severity") for f in c.get("flags", [])]
        cov = c.get("coverage", {})
        out.append({"id": c["id"], "name": (c.get("contacts") or {}).get("name_guess") or c["id"],
                    "readable": c.get("readable", True),
                    "years": (c.get("timeline") or {}).get("years_total"),
                    "demonstrated": sum(1 for v in cov.values() if v.get("status") == "demonstrated"),
                    "requirements": len(cov),
                    "strong": sev.count("strong"), "moderate": sev.count("moderate"), "weak": sev.count("weak"),
                    "top_flag": next((f["title"] for f in c.get("flags", []) if f.get("severity") == "strong"), "")})
    return out


# --------------------------------------------------------------------------- exports

EXPORT_TYPES = {"html": "text/html; charset=utf-8", "pdf": "application/pdf", "csv": "text/csv; charset=utf-8"}


def export(ws, fmt):
    """Return (bytes, filename) for the finished report as html, pdf, or csv. Raises ValueError with a reason."""
    ws = Path(ws)
    rep = ws / (load_state(ws).get("report") or "report.html")
    if not rep.is_file():
        raise ValueError("no report yet")
    sig, ev, req = (read_json(ws / f) for f in ("signals.json", "evals.json", "requirements.json"))
    base = rr.report_basename(req or {}, sig or {}) if sig and req else "candidate-screen"
    if fmt == "html":
        return rep.read_bytes(), base + ".html"
    if fmt == "csv":
        if not (sig and ev and req):
            raise ValueError("signals, evals, or requirements file missing")
        return ("\ufeff" + rr.to_csv(rr.csv_rows(rr.compute(sig, ev, req)[0]))).encode(), base + ".csv"
    if fmt == "pdf":
        pdf = ws / (rep.stem + ".pdf")
        if not pdf.exists() or pdf.stat().st_mtime < rep.stat().st_mtime:
            ok, msg = rr.make_pdf(rep, pdf)
            if not ok:
                raise ValueError(msg)
        return pdf.read_bytes(), base + ".pdf"
    raise ValueError(f"unknown format {fmt}")


# --------------------------------------------------------------------------- server


class App:
    def __init__(self, ws, apps):
        self.ws = Path(ws).expanduser().resolve()
        self.ws.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(18)
        self.last_hit = time.time()
        if not (app_dir(self.ws) / "state.json").exists():
            save_state(self.ws, stage="intake", candidates={}, workspace=str(self.ws),
                       preset_apps=[str(Path(apps).expanduser().resolve())] if apps else [])


def make_handler(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", filename=None):
            data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            if filename:
                self.send_header("Content-Disposition", f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _auth(self, q):
            ok = secrets.compare_digest((q.get("t") or [""])[0], app.token)
            if not ok:
                self._send(403, {"error": "bad token"})
            return ok

        def _body(self, limit=2 * 1024 * 1024):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("too large")
            return self.rfile.read(n)

        def do_GET(self):
            app.last_hit = time.time()
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if not self._auth(q):
                return
            if u.path == "/":
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if u.path == "/api/state":
                st = load_state(app.ws)
                st["requirements"] = read_json(app.ws / "requirements.json")
                st["intake"] = read_json(app_dir(app.ws) / "intake.json")
                st["scan"] = scan_summary(app.ws)
                st["scores"] = read_json(app.ws / "scores.json")
                st["uploads"] = sorted(f.name for f in (app.ws / "applications").glob("*")
                                       if f.is_file()) if (app.ws / "applications").is_dir() else []
                st["can_pick"] = sys.platform == "darwin"
                return self._send(200, st)
            if u.path == "/api/count":
                return self._send(200, {"count": count_apps((q.get("path") or [""])[0])})
            if u.path == "/download":
                fmt = (q.get("fmt") or ["html"])[0]
                try:
                    data, name = export(app.ws, fmt)
                except ValueError as e:
                    return self._send(400, {"error": str(e)})
                return self._send(200, data, EXPORT_TYPES[fmt], filename=name)
            if u.path == "/report":
                rep = app.ws / (load_state(app.ws).get("report") or "report.html")
                if rep.is_file():
                    return self._send(200, rep.read_bytes(), "text/html; charset=utf-8")
                return self._send(404, {"error": "no report yet"})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            app.last_hit = time.time()
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if not self._auth(q):
                return
            try:
                if u.path == "/api/upload":
                    kind = (q.get("kind") or ["app"])[0]
                    name = safe_name((q.get("name") or ["file"])[0])
                    if Path(name).suffix.lower() not in APP_EXT:
                        return self._send(400, {"error": f"unsupported type: {name}"})
                    data = self._body(MAX_UPLOAD)
                    if kind == "posting":
                        dest = app.ws / ("posting" + Path(name).suffix.lower())
                    else:
                        d = app.ws / "applications"
                        d.mkdir(exist_ok=True)
                        dest = d / name
                    dest.write_bytes(data)
                    return self._send(200, {"saved": dest.name})
                if u.path == "/api/remove":
                    name = safe_name(json.loads(self._body()).get("name", ""))
                    f = app.ws / "applications" / name
                    if f.is_file():
                        f.unlink()
                    return self._send(200, {"ok": True})
                if u.path == "/api/pick-folder":
                    if sys.platform != "darwin":
                        return self._send(400, {"error": "folder picker is macOS only; type the path"})
                    r = subprocess.run(["osascript", "-e", 'POSIX path of (choose folder with prompt "Folder of applications")'],
                                       capture_output=True, text=True, timeout=600)
                    path = r.stdout.strip()
                    return self._send(200, {"path": path, "count": count_apps(path) if path else 0})
                if u.path == "/api/save-copy":
                    if sys.platform != "darwin":
                        return self._send(400, {"error": "Save to... is macOS only; use the download buttons"})
                    data, name = export(app.ws, (q.get("fmt") or ["pdf"])[0])
                    script = ('POSIX path of (choose file name with prompt "Save the screening report as" '
                              f'default name "{name}" default location (path to desktop folder))')
                    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
                    dest = r.stdout.strip()
                    if not dest:
                        return self._send(200, {"cancelled": True})
                    Path(dest).write_bytes(data)
                    return self._send(200, {"saved": dest})
                if u.path == "/api/reveal":
                    rep = app.ws / (load_state(app.ws).get("report") or "report.html")
                    if sys.platform == "darwin" and rep.exists():
                        subprocess.run(["open", "-R", str(rep)], timeout=30)
                    return self._send(200, {"ok": True})
                if u.path == "/api/intake":
                    body = json.loads(self._body())
                    if body.get("posting_text", "").strip():
                        (app.ws / "posting.txt").write_text(body["posting_text"])
                    paths = [p for p in body.get("app_paths", []) if p]
                    if (app.ws / "applications").is_dir() and any((app.ws / "applications").iterdir()):
                        paths.append(str(app.ws / "applications"))
                    posting_file = next((str(f) for f in sorted(app.ws.glob("posting.*"))
                                         if f.suffix.lower() in APP_EXT), "")
                    intake = {"role": body.get("role", ""), "company": body.get("company", ""),
                              "posting_url": body.get("posting_url", ""), "posting_file": posting_file,
                              "app_paths": paths, "web_checks": bool(body.get("web_checks")),
                              "legal_requirement": body.get("legal_requirement", ""),
                              "submitted": datetime.now().isoformat(timespec="seconds")}
                    write_json(app_dir(app.ws) / "intake.json", intake)
                    save_state(app.ws, stage="intake_submitted", message="Waiting for Claude to read the posting.")
                    return self._send(200, {"ok": True})
                if u.path == "/api/requirements":
                    req = json.loads(self._body())
                    if not req.get("requirements"):
                        return self._send(400, {"error": "need at least one requirement"})
                    write_json(app.ws / "requirements.json", req)
                    save_state(app.ws, stage="approved", message="Requirements approved. Starting the scan.")
                    return self._send(200, {"ok": True})
                if u.path == "/api/restart":
                    save_state(app.ws, stage="intake", message="", candidates={})
                    return self._send(200, {"ok": True})
            except (ValueError, OSError, subprocess.SubprocessError) as e:
                return self._send(400, {"error": str(e)})
            return self._send(404, {"error": "not found"})

    return H


def cmd_serve(a):
    app = App(a.workspace, a.apps)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(app))
    url = f"http://127.0.0.1:{srv.server_address[1]}/?t={app.token}"
    save_state(app.ws, url=url)
    print(f"GUI: {url}\nworkspace: {app.ws}", flush=True)
    if not a.no_open:
        webbrowser.open(url)

    def idle():
        while True:
            time.sleep(60)
            if time.time() - app.last_hit > IDLE_LIMIT:
                srv.shutdown()
                return
    threading.Thread(target=idle, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_wait(a):
    want = {s.strip() for s in a.stage.split(",")}
    end = time.time() + a.timeout
    while time.time() < end:
        st = load_state(a.workspace)
        if st.get("stage") in want:
            st["intake"] = read_json(app_dir(a.workspace) / "intake.json")
            print(json.dumps(st, indent=2))
            return 0
        time.sleep(1)
    print(json.dumps({"timeout": True, "stage": load_state(a.workspace).get("stage")}))
    return 2


def cmd_stage(a):
    if a.stage not in STAGES:
        sys.exit(f"unknown stage {a.stage}; one of {', '.join(STAGES)}")
    ch = {"stage": a.stage}
    if a.message is not None:
        ch["message"] = a.message
    if a.report:
        ch["report"] = a.report
    save_state(a.workspace, **ch)
    print(f"stage -> {a.stage}")


def cmd_progress(a):
    st = load_state(a.workspace)
    c = st.setdefault("candidates", {})
    c.setdefault(a.candidate, {})["status"] = a.status
    if a.name:
        c[a.candidate]["name"] = a.name
    save_state(a.workspace, candidates=c)
    print(f"{a.candidate} -> {a.status}")


# --------------------------------------------------------------------------- page

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Candidate Screen</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--surface-2:#f0efec;--ink:#0b0b0b;--ink-2:#52514e;--muted:#6f6e69;
--grid:#e1e0d9;--border:rgba(11,11,11,.12);--accent:#2a78d6;--accent-ink:#fff;--good:#0ca30c;--warning:#fab219;--serious:#ec835a;
--critical:#d03b3b;--good-ink:#006300;--warn-ink:#7a5200;--crit-ink:#a32020;--hero-a:#0d366b;--hero-b:#2a78d6;--hero-c:#6250d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#262624;
--ink:#f0efec;--ink-2:#c3c2b7;--muted:#9a9890;--grid:#2c2c2a;--border:rgba(255,255,255,.12);--accent:#3987e5;--good-ink:#0ca30c;
--warn-ink:#fab219;--crit-ink:#e66767;--hero-a:#0d1f3c;--hero-b:#184f95;--hero-c:#4a3aa7}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--surface-2:#262624;--ink:#f0efec;--ink-2:#c3c2b7;
--muted:#9a9890;--grid:#2c2c2a;--border:rgba(255,255,255,.12);--accent:#3987e5;--good-ink:#0ca30c;--warn-ink:#fab219;--crit-ink:#e66767;
--hero-a:#0d1f3c;--hero-b:#184f95;--hero-c:#4a3aa7}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px}
header{background:linear-gradient(120deg,var(--hero-a),var(--hero-b) 55%,var(--hero-c));color:#fff;padding:28px 0 72px}
header h1{margin:0;font-size:28px}header p{margin:4px 0 0;opacity:.88}
.toggle{float:right;background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.35);border-radius:999px;padding:6px 12px;cursor:pointer;font:inherit;font-size:13px}
.stepper{display:flex;gap:6px;margin:20px 0 0;padding:0;list-style:none;flex-wrap:wrap}
.stepper li{display:flex;align-items:center;gap:8px;font-size:13px;padding:6px 12px 6px 6px;border-radius:999px;background:rgba(255,255,255,.12);color:rgba(255,255,255,.75)}
.stepper li b{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;background:rgba(255,255,255,.2);font-size:12px}
.stepper li.on{background:#fff;color:#0d366b;font-weight:600}.stepper li.on b{background:#2a78d6;color:#fff}
.stepper li.done b{background:#0ca30c;color:#fff}
main{margin-top:-48px;padding-bottom:64px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:20px;box-shadow:0 8px 28px rgba(0,0,0,.07);margin-bottom:16px}
.card h2{margin:0 0 4px;font-size:18px}.card .sub{margin:0 0 14px;color:var(--ink-2);font-size:14px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}@media(max-width:820px){.grid2{grid-template-columns:1fr}}
label{display:block;font-size:13px;font-weight:600;margin:10px 0 4px;color:var(--ink-2)}
input[type=text],input[type=url],input[type=number],textarea{width:100%;font:inherit;color:var(--ink);background:var(--page);border:1px solid var(--border);border-radius:10px;padding:9px 11px}
textarea{min-height:220px;resize:vertical;font-size:13px}
input:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
.tabs{display:flex;gap:4px;background:var(--surface-2);padding:4px;border-radius:10px;width:max-content;max-width:100%}
.tabs button{font:inherit;font-size:13px;border:0;background:transparent;color:var(--ink-2);padding:5px 12px;border-radius:7px;cursor:pointer}
.tabs button.on{background:var(--surface);color:var(--ink);box-shadow:0 1px 3px rgba(0,0,0,.12)}
.drop{border:2px dashed var(--grid);border-radius:14px;padding:22px;text-align:center;color:var(--ink-2);transition:.15s;cursor:pointer}
.drop.over{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 8%,transparent)}
.drop b{color:var(--ink)}.drop small{display:block;margin-top:4px;color:var(--muted)}
.btn{font:inherit;font-weight:600;border:1px solid var(--border);background:var(--surface);color:var(--ink);border-radius:10px;padding:9px 16px;cursor:pointer}
.btn.primary{background:var(--accent);color:var(--accent-ink);border-color:transparent}
.btn.primary:disabled{opacity:.45;cursor:not-allowed}.btn.sm{padding:5px 10px;font-size:13px}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.right{margin-left:auto}
.files{list-style:none;margin:12px 0 0;padding:0;max-height:220px;overflow:auto}
.files li{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:8px;font-size:14px}.files li:nth-child(odd){background:var(--surface-2)}
.ext{font-size:10px;font-weight:700;text-transform:uppercase;padding:2px 6px;border-radius:5px;background:var(--accent);color:#fff;min-width:38px;text-align:center}
.x{margin-left:auto;border:0;background:none;color:var(--muted);cursor:pointer;font-size:16px}
.check{display:flex;gap:8px;align-items:flex-start;margin:10px 0;font-size:14px}.check input{margin-top:4px}
.footer-bar{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.hint{font-size:13px;color:var(--muted)}
.wait{display:flex;align-items:center;gap:16px;padding:12px 0}
.spin{width:34px;height:34px;border-radius:50%;border:4px solid var(--surface-2);border-top-color:var(--accent);animation:sp 1s linear infinite;flex:none}
@keyframes sp{to{transform:rotate(360deg)}}
table{border-collapse:collapse;width:100%}th,td{padding:8px;border-bottom:1px solid var(--grid);text-align:left;vertical-align:middle;font-size:14px}
thead th{font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.req td input{padding:6px 8px}
.sw{position:relative;display:inline-block;width:42px;height:24px}.sw input{opacity:0;width:0;height:0}
.sw span{position:absolute;inset:0;background:var(--grid);border-radius:999px;transition:.15s;cursor:pointer}
.sw span:before{content:"";position:absolute;width:18px;height:18px;left:3px;top:3px;background:#fff;border-radius:50%;transition:.15s}
.sw input:checked+span{background:var(--critical)}.sw input:checked+span:before{transform:translateX(18px)}
.mustlbl{font-size:11px;font-weight:700;color:var(--crit-ink);margin-left:6px}
.weights{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px 24px}
.w label{display:flex;justify-content:space-between;margin:0}.w input{width:100%;accent-color:var(--accent)}
.notes{background:var(--surface-2);border-radius:10px;padding:10px 14px;font-size:14px;margin-bottom:12px}.notes ul{margin:4px 0;padding-left:18px}
.pipeline{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 16px;padding:0;list-style:none}
.pipeline li{flex:1;min-width:130px;padding:10px 12px;border-radius:12px;background:var(--surface-2);font-size:13px;color:var(--muted)}
.pipeline li.on{background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--ink);font-weight:600}
.pipeline li.done{color:var(--good-ink)}
.pbar{height:10px;background:var(--surface-2);border-radius:5px;overflow:hidden}.pbar span{display:block;height:100%;background:var(--accent);transition:width .4s}
.cands{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px;margin-top:14px}
.cand{border:1px solid var(--border);border-radius:12px;padding:12px;background:var(--surface)}
.cand b{display:block}.cand .meta{font-size:12px;color:var(--muted)}
.pill{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:2px 9px 2px 3px;border-radius:999px;border:1px solid var(--border);margin:6px 4px 0 0}
.pill i{display:inline-grid;place-items:center;width:16px;height:16px;border-radius:50%;font-style:normal;font-size:10px;color:#fff;background:var(--muted)}
.p-good i{background:var(--good)}.p-warn i{background:var(--warning);color:#0b0b0b}.p-crit i{background:var(--critical)}.p-busy i{background:var(--accent)}
.flagline{font-size:12px;color:var(--crit-ink);margin-top:6px}
.report{width:100%;height:80vh;border:1px solid var(--border);border-radius:14px;background:var(--surface)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
.kpi{background:var(--surface-2);border-radius:12px;padding:12px 14px}.kpi span{font-size:12px;color:var(--ink-2);display:block}.kpi b{font-size:26px}
.save{display:grid;grid-template-columns:1fr 1fr;gap:16px;border-top:1px solid var(--grid);padding-top:14px}
@media(max-width:820px){.save{grid-template-columns:1fr}}
.save b{display:block;margin-bottom:8px;font-size:14px}.save .hint{margin:8px 0 0}
a.btn{text-decoration:none;display:inline-block}a.btn.busy{opacity:.6;pointer-events:none}
.err{background:color-mix(in srgb,var(--critical) 12%,transparent);border-left:3px solid var(--critical);padding:10px 14px;border-radius:8px}
.privacy{font-size:12px;color:var(--muted);margin-top:18px;text-align:center}
.hidden{display:none!important}
</style></head>
<body>
<header><div class="wrap">
  <button class="toggle" id="theme" type="button">Light / dark</button>
  <h1>Candidate Screen</h1>
  <p>Score a stack of applications against a posting. Fit, learning agility, and integrity, with evidence.</p>
  <ol class="stepper" id="stepper">
    <li data-s="1"><b>1</b>Posting &amp; applications</li><li data-s="2"><b>2</b>Requirements</li>
    <li data-s="3"><b>3</b>Screening</li><li data-s="4"><b>4</b>Report</li></ol>
</div></header>
<main class="wrap">

<section id="v-intake" class="hidden">
  <div class="grid2">
    <div class="card">
      <h2>Job posting</h2><p class="sub">Paste it, link it, or drop the file.</p>
      <div class="tabs" role="tablist"><button class="on" data-tab="paste">Paste</button><button data-tab="url">URL</button><button data-tab="file">File</button></div>
      <div data-pane="paste"><label for="ptext">Posting text</label><textarea id="ptext" placeholder="Paste the full job description"></textarea></div>
      <div data-pane="url" class="hidden"><label for="purl">Posting URL</label><input id="purl" type="url" placeholder="https://..."><p class="hint">Claude fetches it and also saves the raw page so hidden text is caught.</p></div>
      <div data-pane="file" class="hidden"><label>Posting file</label><div class="drop" id="pdrop"><b>Drop a .pdf, .docx, .txt, or .html</b><small>or click to choose</small></div>
        <input type="file" id="pfile" class="hidden" accept=".pdf,.docx,.txt,.md,.html,.htm"><p class="hint" id="pfilename"></p></div>
      <div class="grid2"><div><label for="role">Role title</label><input id="role" type="text" placeholder="IT Manager"></div>
      <div><label for="company">Company</label><input id="company" type="text" placeholder="optional"></div></div>
    </div>
    <div class="card">
      <h2>Applications</h2><p class="sub">Drop files or a whole folder, or point at a folder on disk. PDF, Word, text, Markdown, HTML.</p>
      <div class="drop" id="adrop"><b>Drop resumes here</b><small>or click to choose files</small></div>
      <input type="file" id="afiles" class="hidden" multiple accept=".pdf,.docx,.txt,.md,.html,.htm">
      <label for="apath">Or a folder on disk</label>
      <div class="row"><input id="apath" type="text" placeholder="/Users/you/Hiring/it-manager" style="flex:1"><button class="btn sm" id="pick" type="button">Browse...</button></div>
      <p class="hint" id="apathinfo"></p>
      <ul class="files" id="flist"></ul>
    </div>
  </div>
  <div class="card">
    <h2>Options</h2>
    <label class="check"><input type="checkbox" id="webchk"><span><b>Allow brief web checks on employers</b> for flagged candidates only (does each employer exist, at that size, in those years). Never searches the candidate's personal accounts.</span></label>
    <label for="legal">Legal requirement for the role (optional)</label>
    <input id="legal" type="text" placeholder="e.g. US work authorization without sponsorship; must be in NY or CA">
    <div class="footer-bar" style="margin-top:16px"><span class="hint" id="intakehint">Add a posting and at least one application.</span>
      <button class="btn primary right" id="go1" disabled>Draft requirements</button></div>
  </div>
</section>

<section id="v-wait" class="hidden"><div class="card"><div class="wait"><div class="spin"></div><div><h2 id="waittitle">Working</h2><p class="sub" id="waitmsg"></p></div></div></div></section>

<section id="v-req" class="hidden">
  <div class="card">
    <h2>Review requirements</h2><p class="sub">Claude drafted these from the posting. Must-haves drive the recommendation, so keep them to what the job truly cannot do without. Terms are the words and products the scanner looks for.</p>
    <div class="notes hidden" id="rnotes"></div>
    <table class="req"><thead><tr><th style="width:90px">Must-have</th><th style="width:32%">Requirement</th><th>Match terms (comma separated)</th><th style="width:34px"></th></tr></thead><tbody id="rbody"></tbody></table>
    <button class="btn sm" id="radd" style="margin-top:10px">+ Add requirement</button>
  </div>
  <div class="card">
    <h2>Weights</h2><p class="sub">How much each part counts toward the 0-100 fit score. Integrity is scored separately and never mixed in.</p>
    <div class="weights" id="wbox"></div>
    <p class="hint" id="wsum"></p>
    <div class="grid2" style="max-width:420px"><div><label for="tadv">Advance at</label><input id="tadv" type="number" min="0" max="100"></div>
    <div><label for="tcon">Consider at</label><input id="tcon" type="number" min="0" max="100"></div></div>
    <div class="footer-bar" style="margin-top:16px"><button class="btn" id="back1">Back</button><button class="btn primary right" id="go2">Start screening</button></div>
  </div>
</section>

<section id="v-run" class="hidden">
  <div class="card">
    <h2>Screening</h2><p class="sub" id="runmsg"></p>
    <ol class="pipeline" id="pipe"><li data-p="scanning">1. Scan documents</li><li data-p="evaluating">2. Evaluate candidates</li><li data-p="rendering">3. Build report</li></ol>
    <div class="pbar"><span id="pbar" style="width:0%"></span></div><p class="hint" id="pcount"></p>
    <div class="cands" id="cands"></div>
  </div>
</section>

<section id="v-done" class="hidden">
  <div class="card">
    <div class="row" style="align-items:flex-start;flex-wrap:nowrap"><div style="flex:1;min-width:0"><h2>Report ready</h2><p class="sub" id="donepath" style="word-break:break-all"></p></div>
      <div class="row" style="flex:none"><a class="btn" id="openrep" target="_blank" rel="noopener">Open in new tab</a><button class="btn" id="restart">New screen</button></div></div>
    <div class="kpis" id="dkpis"></div>
    <div class="save">
      <div><b>Download</b><div class="row">
        <a class="btn primary" data-dl="pdf">PDF</a><a class="btn" data-dl="html">HTML</a><a class="btn" data-dl="csv">Shortlist CSV</a></div>
        <p class="hint">PDF has every candidate expanded, for printing or sharing. HTML is interactive. CSV imports into a spreadsheet or ATS.</p></div>
      <div class="mac-only"><b>Save a copy</b><div class="row">
        <button class="btn" data-save="pdf">Save PDF to...</button><button class="btn" data-save="html">Save HTML to...</button>
        <button class="btn" id="reveal">Show in Finder</button></div>
        <p class="hint" id="savemsg">Opens a save dialog so you can pick the folder.</p></div>
    </div>
  </div>
  <iframe class="report" id="repframe" title="Screening report"></iframe>
</section>

<section id="v-error" class="hidden"><div class="card"><h2>Something went wrong</h2><p class="err" id="errmsg"></p><button class="btn" id="restart2">Start over</button></div></section>

<p class="privacy">Runs on this computer only. Applications stay in the workspace folder; nothing is uploaded.</p>
</main>
<script>
(function(){
const T=new URLSearchParams(location.search).get('t');
const $=s=>document.querySelector(s);
const api=(p,o)=>fetch(p+(p.includes('?')?'&':'?')+'t='+encodeURIComponent(T),o).then(r=>r.json().then(j=>{if(!r.ok)throw new Error(j.error||r.status);return j}));
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const root=document.documentElement;
try{const t=localStorage.getItem('cs-theme');if(t)root.setAttribute('data-theme',t)}catch(e){}
$('#theme').onclick=()=>{const d=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme: dark)').matches);
  const n=d?'light':'dark';root.setAttribute('data-theme',n);try{localStorage.setItem('cs-theme',n)}catch(e){}};

let state={},view='',postingFile='',appPathCount=0,reqLoaded=false;
const VIEWS={intake:'intake',intake_submitted:'wait',drafting:'wait',requirements_review:'req',approved:'run',scanning:'run',evaluating:'run',rendering:'run',done:'done',error:'error'};
const STEP={intake:1,intake_submitted:1,drafting:1,requirements_review:2,approved:3,scanning:3,evaluating:3,rendering:3,done:4,error:1};

function show(v){document.querySelectorAll('main>section').forEach(s=>s.classList.toggle('hidden',s.id!=='v-'+v));view=v}
function stepper(n){document.querySelectorAll('#stepper li').forEach(li=>{const s=+li.dataset.s;li.classList.toggle('on',s===n);li.classList.toggle('done',s<n)})}

// tabs
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));
  document.querySelectorAll('[data-pane]').forEach(p=>p.classList.toggle('hidden',p.dataset.pane!==b.dataset.tab));validate()});

// uploads
async function upload(file,kind){const r=await fetch('/api/upload?kind='+kind+'&name='+encodeURIComponent(file.name)+'&t='+encodeURIComponent(T),{method:'POST',body:file});
  const j=await r.json();if(!r.ok)throw new Error(j.error);return j}
const OK=/\.(pdf|docx|txt|md|html?)$/i;
async function addFiles(files){let bad=[];for(const f of files){if(!OK.test(f.name)){bad.push(f.name);continue}
  try{await upload(f,'app')}catch(e){bad.push(f.name+' ('+e.message+')')}}
  if(bad.length)alert('Skipped: '+bad.join(', '));refresh()}
async function walk(entry,out){if(entry.isFile){await new Promise(r=>entry.file(f=>{out.push(f);r()},r))}
  else if(entry.isDirectory&&!/^[._]/.test(entry.name)){const rd=entry.createReader();let batch;do{batch=await new Promise(r=>rd.readEntries(r,()=>r([])));for(const e of batch)await walk(e,out)}while(batch.length)}}
function dropzone(el,input,onFiles){el.onclick=()=>input.click();input.onchange=()=>onFiles([...input.files]);
  el.ondragover=e=>{e.preventDefault();el.classList.add('over')};el.ondragleave=()=>el.classList.remove('over');
  el.ondrop=async e=>{e.preventDefault();el.classList.remove('over');const out=[];const items=[...(e.dataTransfer.items||[])];
    if(items.length&&items[0].webkitGetAsEntry){for(const it of items){const en=it.webkitGetAsEntry();if(en)await walk(en,out)}}else out.push(...e.dataTransfer.files);
    onFiles(out)}}
dropzone($('#adrop'),$('#afiles'),addFiles);
dropzone($('#pdrop'),$('#pfile'),async fs=>{const f=fs[0];if(!f)return;try{await upload(f,'posting');postingFile=f.name;$('#pfilename').textContent='Saved: '+f.name;validate()}catch(e){alert(e.message)}});

$('#pick').onclick=async()=>{try{const j=await api('/api/pick-folder',{method:'POST'});if(j.path){$('#apath').value=j.path;pathInfo(j.count)}}catch(e){alert(e.message)}};
let pt;$('#apath').oninput=()=>{clearTimeout(pt);pt=setTimeout(async()=>{const v=$('#apath').value.trim();if(!v){pathInfo(null);return}
  const j=await api('/api/count?path='+encodeURIComponent(v));pathInfo(j.count)},350)};
function pathInfo(n){appPathCount=n>0?n:0;$('#apathinfo').textContent=n==null?'':n<0?'Path not found':n===0?'No supported files in that folder':n+' application file'+(n===1?'':'s')+' found';validate()}

function renderFiles(list){$('#flist').innerHTML=list.map(n=>`<li><span class="ext">${esc(n.split('.').pop())}</span>${esc(n)}<button class="x" data-n="${esc(n)}" title="Remove">&times;</button></li>`).join('');
  document.querySelectorAll('#flist .x').forEach(b=>b.onclick=async()=>{await api('/api/remove',{method:'POST',body:JSON.stringify({name:b.dataset.n})});refresh()})}

function activeTab(){return document.querySelector('.tabs button.on').dataset.tab}
function validate(){const tab=activeTab();const hasPost=tab==='paste'?$('#ptext').value.trim().length>80:tab==='url'?/^https?:\/\//.test($('#purl').value.trim()):!!postingFile;
  const hasApps=(state.uploads||[]).length>0||appPathCount>0;$('#go1').disabled=!(hasPost&&hasApps);
  $('#intakehint').textContent=!hasPost?'Add the job posting.':!hasApps?'Add at least one application.':'Ready. Claude will draft the requirements for you to review.'}
['#ptext','#purl'].forEach(s=>$(s).addEventListener('input',validate));

$('#go1').onclick=async()=>{const tab=activeTab();$('#go1').disabled=true;
  try{await api('/api/intake',{method:'POST',body:JSON.stringify({posting_text:tab==='paste'?$('#ptext').value:'',posting_url:tab==='url'?$('#purl').value.trim():'',
    role:$('#role').value.trim(),company:$('#company').value.trim(),app_paths:appPathCount>0?[$('#apath').value.trim()]:[],
    web_checks:$('#webchk').checked,legal_requirement:$('#legal').value.trim()})});refresh()}catch(e){alert(e.message);validate()}};

// requirements editor
const DIMS=[['must_have','Must-have skills'],['experience','Relevant experience'],['impact','Demonstrated impact'],['learning_agility','Learning agility'],['work_style','Work-style signals'],['nice_to_have','Nice-to-haves']];
const DEFW={must_have:30,experience:25,impact:15,learning_agility:15,work_style:5,nice_to_have:10};
let reqMeta={};
function reqRow(r){const tr=document.createElement('tr');tr.innerHTML=`<td><label class="sw"><input type="checkbox" ${r.must?'checked':''}><span></span></label></td>
  <td><input type="text" class="rl" value="${esc(r.label)}" title="${esc(r.text||'')}"></td><td><input type="text" class="rt" value="${esc((r.terms||[]).join(', '))}"></td>
  <td><button class="x" title="Remove">&times;</button></td>`;tr.dataset.id=r.id||'';tr.dataset.text=r.text||'';tr.querySelector('.x').onclick=()=>tr.remove();return tr}
function loadReq(req){reqMeta=req||{};const b=$('#rbody');b.innerHTML='';(req.requirements||[]).forEach(r=>b.appendChild(reqRow(r)));
  const n=req.notes||[];$('#rnotes').classList.toggle('hidden',!n.length);$('#rnotes').innerHTML='<b>Notes from Claude</b><ul>'+n.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';
  const w=Object.assign({},DEFW,req.weights||{});$('#wbox').innerHTML=DIMS.map(([k,l])=>`<div class="w"><label>${l}<span id="wv-${k}">${w[k]}</span></label><input type="range" min="0" max="50" step="5" data-k="${k}" value="${w[k]}"></div>`).join('');
  document.querySelectorAll('#wbox input').forEach(i=>i.oninput=wsum);wsum();const th=Object.assign({advance:75,consider:60},req.thresholds||{});$('#tadv').value=th.advance;$('#tcon').value=th.consider}
function wsum(){let s=0;document.querySelectorAll('#wbox input').forEach(i=>{s+=+i.value;$('#wv-'+i.dataset.k).textContent=i.value});$('#wsum').textContent='Total '+s+' (scores are normalized, so the total does not need to be 100).'}
$('#radd').onclick=()=>$('#rbody').appendChild(reqRow({label:'',terms:[],must:false}));
$('#back1').onclick=async()=>{if(confirm('Go back to the posting and applications? The draft requirements will be redrafted.')){await api('/api/restart',{method:'POST'});reqLoaded=false;refresh()}};
$('#go2').onclick=async()=>{const rows=[...document.querySelectorAll('#rbody tr')];let n=0;
  const reqs=rows.map(tr=>{const label=tr.querySelector('.rl').value.trim();if(!label)return null;n++;return{id:tr.dataset.id||('R'+(100+n)),label,
    terms:tr.querySelector('.rt').value.split(',').map(s=>s.trim()).filter(Boolean),must:tr.querySelector('input[type=checkbox]').checked,text:tr.dataset.text||label}}).filter(Boolean);
  const ids=new Set();reqs.forEach((r,i)=>{if(ids.has(r.id))r.id='R'+(200+i);ids.add(r.id)});
  if(!reqs.some(r=>r.must)&&!confirm('No must-haves. Continue anyway?'))return;
  const weights={};document.querySelectorAll('#wbox input').forEach(i=>weights[i.dataset.k]=+i.value);
  const body=Object.assign({},reqMeta,{requirements:reqs,weights,thresholds:{advance:+$('#tadv').value||75,consider:+$('#tcon').value||60}});
  try{await api('/api/requirements',{method:'POST',body:JSON.stringify(body)});refresh()}catch(e){alert(e.message)}};

// progress
function renderRun(st){const order=['scanning','evaluating','rendering'];const cur=st.stage==='approved'?-1:order.indexOf(st.stage);
  document.querySelectorAll('#pipe li').forEach((li,i)=>{li.classList.toggle('on',i===cur);li.classList.toggle('done',i<cur)});
  $('#runmsg').textContent=st.message||'';const scan=st.scan||[];const prog=st.candidates||{};
  const ids=scan.length?scan.map(c=>c.id):Object.keys(prog);const done=ids.filter(id=>(prog[id]||{}).status==='done').length;
  const pct=st.stage==='rendering'?100:ids.length?Math.round(100*done/ids.length):(st.stage==='scanning'?8:3);$('#pbar').style.width=pct+'%';
  $('#pcount').textContent=ids.length?done+' of '+ids.length+' evaluated':'';
  $('#cands').innerHTML=ids.map(id=>{const c=scan.find(x=>x.id===id)||{id};const p=(prog[id]||{}).status||'queued';const name=(prog[id]||{}).name||c.name||id;
    const integ=c.strong?`<span class="pill p-crit"><i>&#x2715;</i>${c.strong} strong flag${c.strong>1?'s':''}</span>`:c.moderate?`<span class="pill p-warn"><i>!</i>${c.moderate} to verify</span>`:(c.requirements!=null?'<span class="pill p-good"><i>&#x2713;</i>No flags</span>':'');
    const ps=p==='done'?'<span class="pill p-good"><i>&#x2713;</i>Evaluated</span>':p==='scoring'?'<span class="pill p-busy"><i>&hellip;</i>Scoring</span>':'<span class="pill"><i>&middot;</i>Queued</span>';
    return `<div class="cand"><b>${esc(name)}</b><span class="meta">${c.years!=null?esc(c.years)+' yrs dated roles &middot; ':''}${c.requirements!=null?c.demonstrated+'/'+c.requirements+' requirements shown in roles':''}</span><div>${ps}${integ}</div>${c.top_flag?'<div class="flagline">'+esc(c.top_flag)+'</div>':''}</div>`}).join('')}

function renderDone(st){$('#donepath').textContent='Saved to '+(st.workspace||'')+'/'+(st.report||'report.html');
  const u='/report?t='+encodeURIComponent(T);$('#openrep').href=u;if($('#repframe').dataset.src!==st.updated){$('#repframe').src=u;$('#repframe').dataset.src=st.updated}
  const s=st.scores||[];const c=r=>s.filter(x=>x.rec===r).length;
  $('#dkpis').innerHTML=[['Applications',s.length],['Advance',c('Advance')],['Consider',c('Consider')],['Verify first',c('Verify first')],['Pass',c('Pass')]].map(([k,v])=>`<div class="kpi"><span>${k}</span><b>${v}</b></div>`).join('')}
document.querySelectorAll('[data-dl]').forEach(a=>{a.href='/download?fmt='+a.dataset.dl+'&t='+encodeURIComponent(T);
  a.onclick=async e=>{if(a.dataset.dl!=='pdf')return;e.preventDefault();const old=a.textContent;a.textContent='Building PDF...';a.classList.add('busy');
    try{const r=await fetch(a.href);if(!r.ok)throw new Error((await r.json()).error);const b=await r.blob();
      const name=(r.headers.get('Content-Disposition')||'').match(/filename="([^"]+)"/);const l=document.createElement('a');l.href=URL.createObjectURL(b);
      l.download=name?name[1]:'report.pdf';document.body.appendChild(l);l.click();setTimeout(()=>{URL.revokeObjectURL(l.href);l.remove()},1000)}
    catch(err){alert(err.message)}finally{a.textContent=old;a.classList.remove('busy')}}});
document.querySelectorAll('[data-save]').forEach(b=>b.onclick=async()=>{const m=$('#savemsg');m.textContent=b.dataset.save==='pdf'?'Building PDF...':'Choose where to save...';
  try{const j=await api('/api/save-copy?fmt='+b.dataset.save,{method:'POST'});m.textContent=j.saved?'Saved to '+j.saved:'Save cancelled.'}catch(e){m.textContent=e.message}});
$('#reveal').onclick=()=>api('/api/reveal',{method:'POST'});
$('#restart').onclick=$('#restart2').onclick=async()=>{if(confirm('Start a new screen in this workspace? Tell Claude in chat as well.')){await api('/api/restart',{method:'POST'});reqLoaded=false;refresh()}};

const WAIT={intake_submitted:['Handing off to Claude','Claude is picking up the posting and applications.'],drafting:['Drafting requirements','Claude is reading the posting and separating true must-haves from wish-list items.']};
async function refresh(){try{state=await api('/api/state')}catch(e){return}
  const v=VIEWS[state.stage]||'intake';stepper(STEP[state.stage]||1);
  if(v==='intake'){if(view!=='intake'&&(state.preset_apps||[]).length&&!$('#apath').value){$('#apath').value=state.preset_apps[0];$('#apath').oninput()}renderFiles(state.uploads||[]);validate()}
  if(v==='wait'){const w=WAIT[state.stage]||['Working',''];$('#waittitle').textContent=w[0];$('#waitmsg').textContent=state.message||w[1]}
  if(v==='req'&&!reqLoaded&&state.requirements){loadReq(state.requirements);reqLoaded=true}
  document.querySelectorAll('.mac-only').forEach(el=>el.classList.toggle('hidden',!state.can_pick));
  if(v==='run')renderRun(state);if(v==='done')renderDone(state);if(v==='error')$('#errmsg').textContent=state.message||'Unknown error';
  if(v!==view)show(v)}
refresh();setInterval(()=>{if(view!=='req'||!reqLoaded)refresh()},1500);
})();
</script></body></html>"""


# --------------------------------------------------------------------------- selftest


def selftest():
    import tempfile
    import urllib.request
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + msg)
        ok = ok and cond

    with tempfile.TemporaryDirectory() as td:
        app = App(td, None)
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def req(path, data=None, tok=True):
            url = base + path + (("&" if "?" in path else "?") + "t=" + app.token if tok else "")
            r = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
            try:
                with urllib.request.urlopen(r) as resp:
                    return resp.status, resp.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()

        check(req("/api/state", tok=False)[0] == 403, "request without token is refused")
        code, body = req("/")
        check(code == 200 and b"Candidate Screen" in body, "page served with token")
        code, _ = req("/api/upload?kind=app&name=../../evil%20resume.txt", b"x" * 50)
        saved = list((Path(td) / "applications").glob("*"))
        check(code == 200 and len(saved) == 1 and saved[0].name == "evil resume.txt", "upload name sanitized into workspace")
        check(req("/api/upload?kind=app&name=run.sh", b"x")[0] == 400, "unsupported upload type refused")
        req("/api/intake", json.dumps({"posting_text": "A posting " * 20, "role": "IT Manager"}).encode())
        st = json.loads(req("/api/state")[1])
        check(st["stage"] == "intake_submitted" and st["intake"]["app_paths"], "intake moves stage and records upload folder")
        check((Path(td) / "posting.txt").exists(), "posting text saved")
        save_state(td, stage="requirements_review")
        req("/api/requirements", json.dumps({"role": "x", "requirements": [{"id": "R1", "label": "Mac", "must": True}]}).encode())
        check(load_state(td)["stage"] == "approved" and (Path(td) / "requirements.json").exists(), "approval writes requirements")
        check(req("/download?fmt=html")[0] == 400, "download before a report exists is refused cleanly")
        (Path(td) / "report.html").write_text("<html><body>report</body></html>")
        save_state(td, report="report.html")
        code, body = req("/download?fmt=html")
        check(code == 200 and b"report" in body, "HTML download served")
        check(req("/download?fmt=html", tok=False)[0] == 403, "download without token is refused")
        a = argparse.Namespace(workspace=td, candidate="c1", status="done", name="C One")
        cmd_progress(a)
        check(load_state(td)["candidates"]["c1"]["status"] == "done", "progress recorded")
        srv.shutdown()
    print("all passed" if ok else "FAILURES")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--workspace", required=True)
    s.add_argument("--apps")
    s.add_argument("--port", type=int, default=0)
    s.add_argument("--no-open", action="store_true")
    w = sub.add_parser("wait")
    w.add_argument("--workspace", required=True)
    w.add_argument("--stage", required=True)
    w.add_argument("--timeout", type=int, default=3600)
    g = sub.add_parser("stage")
    g.add_argument("--workspace", required=True)
    g.add_argument("--stage", required=True)
    g.add_argument("--message")
    g.add_argument("--report")
    p = sub.add_parser("progress")
    p.add_argument("--workspace", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--status", required=True, choices=["queued", "scoring", "done"])
    p.add_argument("--name")
    sub.add_parser("selftest")
    a = ap.parse_args()
    if a.cmd == "serve":
        cmd_serve(a)
    elif a.cmd == "wait":
        sys.exit(cmd_wait(a))
    elif a.cmd == "stage":
        cmd_stage(a)
    elif a.cmd == "progress":
        cmd_progress(a)
    else:
        sys.exit(selftest())


if __name__ == "__main__":
    main()
