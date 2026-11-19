#!/usr/bin/env python3
"""Pull current openings straight from employers' public job feeds (Greenhouse, Lever, Ashby). Stdlib only.

  ats_scan.py --company ramp --company stripe:greenhouse --keyword "sales manager" \
              --location Columbus --location Remote --days 30

Prints one tab-separated line per match: company, title, location, posted, url, provider.
Company is a board slug (the last part of boards.greenhouse.io/<slug>, jobs.lever.co/<slug>,
jobs.ashbyhq.com/<slug>). Without ":provider" all three are tried. Titles are matched by keyword;
locations by substring (omit --location to keep everything). Companies with no feed are listed on stderr.
"""
import argparse, json, sys, urllib.request
from datetime import datetime, timedelta, timezone

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{}/jobs",
    "lever": "https://api.lever.co/v0/postings/{}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{}",
}


def fetch(provider, slug):
    req = urllib.request.Request(URLS[provider].format(slug), headers={"User-Agent": "job-search-starter"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def parse_date(v):
    if not v:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v / 1000, timezone.utc)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:  # Python before 3.11 rejects some fractions and offsets; the date and time are enough
        d = datetime.fromisoformat(str(v)[:19])
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def normalize(provider, data):
    """Return dicts with title, location, posted (datetime or None), url."""
    out = []
    if provider == "greenhouse":
        for j in data.get("jobs", []):
            out.append({"title": j.get("title", ""), "location": (j.get("location") or {}).get("name", ""),
                        "posted": parse_date(j.get("first_published") or j.get("updated_at")), "url": j.get("absolute_url", "")})
    elif provider == "lever":
        for j in data if isinstance(data, list) else []:
            c = j.get("categories") or {}
            loc = " | ".join(c.get("allLocations") or [c.get("location") or ""]) + (f" ({j['workplaceType']})" if j.get("workplaceType") else "")
            out.append({"title": j.get("text", ""), "location": loc, "posted": parse_date(j.get("createdAt")), "url": j.get("hostedUrl", "")})
    elif provider == "ashby":
        for j in data.get("jobs", []):
            locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
            if j.get("isRemote"):
                locs.append("Remote")
            out.append({"title": (j.get("title") or "").strip(), "location": " | ".join(x for x in locs if x),
                        "posted": parse_date(j.get("publishedAt")), "url": j.get("jobUrl", "")})
    return out


def keep(job, keywords, locations, cutoff):
    t, l = job["title"].lower(), job["location"].lower()
    if keywords and not any(k.lower() in t for k in keywords):
        return False
    if locations and not any(x.lower() in l for x in locations):
        return False
    return not (cutoff and job["posted"] and job["posted"] < cutoff)  # undated postings are kept, not dropped


def main(argv=None, fetch=fetch):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--company", action="append", required=True)
    p.add_argument("--keyword", action="append", default=[])
    p.add_argument("--location", action="append", default=[])
    p.add_argument("--days", type=int, default=0)
    a = p.parse_args(argv)
    cutoff = datetime.now(timezone.utc) - timedelta(days=a.days) if a.days else None
    for c in a.company:
        slug, _, prov = c.partition(":")
        found = False
        for provider in [prov] if prov else URLS:
            if provider not in URLS:
                sys.exit(f"unknown provider {provider}")
            try:
                jobs = normalize(provider, fetch(provider, slug))
            except Exception:
                continue
            if not jobs:
                continue
            found = True
            for j in jobs:
                if keep(j, a.keyword, a.location, cutoff):
                    d = j["posted"].date().isoformat() if j["posted"] else "undated"
                    print("\t".join([slug, j["title"], j["location"], d, j["url"], provider]))
            break
        if not found:
            print(f"no feed found for {slug}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a code page that cannot print every character
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
