#!/usr/bin/env python3
"""Job tracker CSV for job-search-starter. Stdlib only.

  tracker.py add --company X --title Y [--location L --url U --pay P --fit N --status S --notes T]
  tracker.py seen --company X --title Y [--location L --url U]     exit 0 if already tracked, 1 if new
  tracker.py update ID [--status S --fit 1-5 --followup YYYY-MM-DD --notes T --pay P --sent]
  tracker.py list [--status S]
  tracker.py due                                      follow-ups due (stops after 2 sent; --sent counts one)
  tracker.py summary
Default file: job-search/tracker.csv (override with --file).
"""
import argparse, csv, os, re, sys
from datetime import date

COLS = ["id", "date", "company", "title", "location", "url", "status", "pay", "fit", "followup", "nudges", "notes"]
STATUSES = ["found", "reviewed", "passed", "applied", "interviewing", "offer", "accepted", "rejected", "withdrawn"]
OPEN = {"applied", "interviewing"}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def jobid(url):
    m = re.search(r"/jobs/view/(?:[^/?]*-)?(\d{6,})", url or "")
    return m.group(1) if m else ""


DANGER = "=+-@"


def guard(v):  # postings are untrusted; Excel runs cells that start with = + - @ as formulas
    return "'" + v if v[:1] in DANGER and v else v


def unguard(v):
    return v[1:] if v[:1] == "'" and v[1:2] in DANGER and v[1:2] else v


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads accents
        return [{k: unguard(v or "") for k, v in r.items()} for r in csv.DictReader(f)]


def save(path, rows):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows({k: guard(str(v)) for k, v in r.items()} for r in rows)


def find_dup(rows, company, title, url, location=""):
    jid = jobid(url)
    for r in rows:
        if jid and jobid(r.get("url")) == jid:
            return r
        if norm(r.get("company")) == norm(company) and norm(r.get("title")) == norm(title):
            rl = norm(r.get("location"))
            if rl and norm(location) and rl != norm(location):
                continue  # same job title in a different place is a different job
            return r
    return None


def check_status(s):
    if s not in STATUSES:
        sys.exit(f"status must be one of: {', '.join(STATUSES)}")


def check_fit(s):
    if s not in ("1", "2", "3", "4", "5"):
        sys.exit("fit must be a whole number from 1 to 5")


def check_date(s):
    try:
        date.fromisoformat(s)
    except ValueError:
        sys.exit("followup must be YYYY-MM-DD")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", default="job-search/tracker.csv")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("add", "seen"):
        s = sub.add_parser(name)
        s.add_argument("--company", required=True)
        s.add_argument("--title", required=True)
        s.add_argument("--url", default="")
        s.add_argument("--location", default="")
    sub.choices["add"].add_argument("--pay", default="")
    sub.choices["add"].add_argument("--fit", default="")
    sub.choices["add"].add_argument("--status", default="found")
    sub.choices["add"].add_argument("--notes", default="")
    u = sub.add_parser("update")
    u.add_argument("id")
    u.add_argument("--sent", action="store_true", help="count one follow-up sent")
    for k in ("status", "fit", "followup", "notes", "pay"):
        u.add_argument(f"--{k}")
    l = sub.add_parser("list")
    l.add_argument("--status")
    sub.add_parser("due")
    sub.add_parser("summary")
    a = p.parse_args(argv)
    rows = load(a.file)

    if a.cmd == "seen":
        d = find_dup(rows, a.company, a.title, a.url, a.location)
        print(d["id"] if d else "new")
        return 0 if d else 1
    if a.cmd == "add":
        check_status(a.status)
        if a.fit:
            check_fit(a.fit)
        d = find_dup(rows, a.company, a.title, a.url, a.location)
        if d:
            print(f"duplicate {d['id']}")
            return 0
        n = max([int(r["id"]) for r in rows if r.get("id", "").isdigit()] + [0]) + 1
        rows.append({"id": str(n), "date": date.today().isoformat(), "company": a.company, "title": a.title,
                     "location": a.location, "nudges": "0", "url": a.url, "status": a.status, "pay": a.pay, "fit": a.fit, "followup": "", "notes": a.notes})
        save(a.file, rows)
        print(f"added {n}")
        return 0
    if a.cmd == "update":
        r = next((r for r in rows if r["id"] == a.id), None)
        if not r:
            sys.exit(f"no row with id {a.id}")
        if a.status:
            check_status(a.status)
        if a.followup:
            check_date(a.followup)
        if a.fit:
            check_fit(a.fit)
        if a.sent:
            r["nudges"] = str(int(r.get("nudges") or 0) + 1)
        for k in ("status", "fit", "followup", "pay"):
            if getattr(a, k):
                r[k] = getattr(a, k)
        if a.notes:  # append so history is kept
            r["notes"] = (r["notes"] + " | " if r["notes"] else "") + f"{date.today().isoformat()}: {a.notes}"
        save(a.file, rows)
        print(f"updated {a.id}")
        return 0
    if a.cmd == "list":
        for r in rows:
            if not a.status or r["status"] == a.status:
                print(f"{r['id']}\t{r['status']}\t{r['fit']}\t{r['company']}\t{r['title']}\t{r['followup']}")
        return 0
    if a.cmd == "due":
        today = date.today().isoformat()
        for r in rows:
            if r["status"] in OPEN and r["followup"] and r["followup"] <= today and int(r.get("nudges") or 0) < 2:
                print(f"{r['id']}\t{r['followup']}\t{r['status']}\t{r['company']}\t{r['title']}")
        return 0
    if a.cmd == "summary":
        for s in STATUSES:
            c = sum(1 for r in rows if r["status"] == s)
            if c:
                print(f"{s}\t{c}")
        return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a code page that cannot print every character
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
