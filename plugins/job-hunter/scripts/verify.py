#!/usr/bin/env python3
"""Check a finished application before the user sends it. Stdlib only.

  verify.py --resume resume.md [--docx R.docx --pdf R.pdf] [--letter cover-letter.md --letter-pdf L.pdf]
            [--posting posting.txt] [--career career.md] [--keyword "forklift" ...] [--max-pages 2]

FAIL (exit 1, fix and rerun):
  copied posting text   8+ words in a row copied from the posting (a short "quoted" line in the letter is fine)
  repeated stat         the same number used 3+ times on the resume
  banned phrasing       stock AI and resume phrases, em dashes
  pages                 resume over --max-pages, letter over 1
  parse                 what an applicant system reads from the .docx: name, email or phone, section headings, dates
REVIEW (read it in context; the script cannot decide):
  untraced number       a number on the resume or letter that is not in career.md
  repeated opener       the same first word on 3+ bullets
  weak opener           "responsible for", "helped", "assisted", "worked on"
  missing keyword       a --keyword not found on the resume
"""
import argparse
import re
import sys
import zipfile
from html import unescape
from pathlib import Path

BANNED = [
    "passionate", "results-driven", "results-oriented", "proven track record", "leverage", "leveraged", "spearheaded",
    "synergy", "synergies", "robust", "seamless", "cutting-edge", "innovative", "best practices", "dynamic",
    "i am writing to", "fast-paced", "utilize", "utilized", "delve", "tapestry", "testament to", "ever-evolving",
    "in today's", "thrilled", "excited to", "hit the ground running", "game-changer", "holistic", "world-class",
    "team player", "detail-oriented", "go-getter", "self-starter", "think outside the box",
]
WEAK = re.compile(r"^(?:responsible for|helped|assisted|worked on|participated in|duties included)\b", re.I)
NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?\s*(?:%|\+|k\b|m\b|million|billion)?", re.I)
YEAR = re.compile(r"^(?:19|20)\d\d$")


def words(text):
    return re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))


def copied_runs(posting, text, n=8):
    p = words(posting)
    grams = {tuple(p[i:i + n]) for i in range(len(p) - n + 1)}
    t, hits, i = words(text), [], 0
    while i <= len(t) - n:
        if tuple(t[i:i + n]) in grams:
            j = i + n
            while j < len(t) and tuple(t[j - n + 1:j + 1]) in grams:
                j += 1
            hits.append(" ".join(t[i:j]))
            i = j
        else:
            i += 1
    return hits


def body_lines(md):
    """Bullets and paragraphs only: skip the name, contact, headings, and role/date lines."""
    out, in_body = [], False
    for ln in md.splitlines():
        s = ln.strip()
        if s.startswith("## "):
            in_body = True
            continue
        if in_body and s and not s.startswith("#"):
            out.append(s)
    return out


def numbers(text):
    out = []
    for m in NUM.finditer(text):
        raw = m.group(0).strip()
        core = re.sub(r"[^\d.]", "", raw).rstrip(".")
        if not core or YEAR.match(core) or (len(core) == 1 and raw == core):
            continue  # years and bare single digits are noise
        out.append((raw, core))
    return out


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    xml = xml.replace("</w:p>", "\n").replace("<w:tab/>", "\t")
    return unescape(re.sub(r"<[^>]+>", "", xml))


def pdf_pages(path):
    counts = re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", Path(path).read_bytes())
    return max(int(c) for c in counts) if counts else 0


def check(a):
    fails, reviews, passes = [], [], []
    resume = Path(a.resume).read_text(encoding="utf-8")
    letter = Path(a.letter).read_text(encoding="utf-8") if a.letter else ""
    posting = Path(a.posting).read_text(encoding="utf-8", errors="replace") if a.posting else ""
    career = Path(a.career).read_text(encoding="utf-8") if a.career else ""
    body = body_lines(resume)

    if posting:
        letter_unquoted = re.sub(r"[\"“][^\"”]{0,250}[\"”]", " ", letter)
        hits = [("resume", h) for h in copied_runs(posting, resume)] + [("letter", h) for h in copied_runs(posting, letter_unquoted)]
        for where, h in hits:
            fails.append(f"copied posting text ({where}): \"{h}\". Say it in your own words.")
        if not hits:
            passes.append("no 8+ word runs copied from the posting")

    counts = {}
    for ln in body:
        for raw, core in numbers(ln):
            counts.setdefault(core, []).append(raw)
    for core, raws in counts.items():
        if len(raws) > 2:
            fails.append(f"repeated stat: {raws[0]} appears {len(raws)} times; keep it to 2 places")

    for name, text in (("resume", resume), ("letter", letter)):
        low = text.lower()
        for b in BANNED:
            if re.search(r"(?<![a-z])" + re.escape(b) + r"(?![a-z])", low):
                fails.append(f"banned phrasing ({name}): \"{b}\"")
        if "—" in text or " -- " in text:
            fails.append(f"em dash ({name}): use a comma, period, or parentheses")

    if a.pdf:
        n = pdf_pages(a.pdf)
        (fails if n > a.max_pages else passes).append(f"resume pages: {n} (limit {a.max_pages})")
    if a.letter_pdf:
        n = pdf_pages(a.letter_pdf)
        (fails if n > 1 else passes).append(f"letter pages: {n} (limit 1)")

    if a.docx:
        t = docx_text(a.docx)
        first = next((ln.strip() for ln in resume.splitlines() if ln.strip()), "").lstrip("# ").strip()
        missing = []
        if first and first not in t:
            missing.append("name")
        if not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", t) and not re.search(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", t):
            missing.append("email or phone")
        heads = [ln.strip()[3:].upper() for ln in resume.splitlines() if ln.strip().startswith("## ")]
        if not heads or any(h not in t for h in heads):
            missing.append("section headings")
        roles = [ln for ln in resume.splitlines() if ln.strip().startswith("### ")]
        if roles and not re.search(r"(?:19|20)\d\d", t):
            missing.append("dates")
        if missing:
            fails.append("parse: an applicant system could not find " + ", ".join(missing) + " in the .docx text")
        else:
            passes.append("parse: name, contact, headings, and dates all readable in the .docx")

    if career:
        career_nums = {core for _, core in numbers(career)} | set(re.findall(r"\d[\d.]*", career.replace(",", "")))
        for text, where in [(" ".join(body), "resume"), (letter, "letter")]:
            seen = set()
            for raw, core in numbers(text):
                if core not in career_nums and core.replace(",", "") not in career_nums and core not in seen:
                    seen.add(core)
                    reviews.append(f"untraced number ({where}): {raw} is not in career.md. Trace it or remove it.")

    bullets = [ln[2:].strip() for ln in resume.splitlines() if ln.strip()[:2] in ("- ", "* ")]
    openers = {}
    for b in bullets:
        w = (words(b) or [""])[0]
        openers[w] = openers.get(w, 0) + 1
        if WEAK.search(b):
            reviews.append(f"weak opener: \"{b[:60]}\"")
    for w, c in openers.items():
        if w and c >= 3:
            reviews.append(f"repeated opener: {c} bullets start with \"{w}\"")

    if a.keyword:
        low = resume.lower()
        found = [k for k in a.keyword if k.lower() in low]
        for k in a.keyword:
            if k not in found:
                reviews.append(f"missing keyword: {k} (add it only if career.md backs it)")
        passes.append(f"keywords: {len(found)}/{len(a.keyword)}")
    return fails, reviews, passes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resume", required=True, help="resume Markdown source")
    ap.add_argument("--docx", help="rendered resume .docx, for the parse check")
    ap.add_argument("--pdf", help="rendered resume .pdf, for the page count")
    ap.add_argument("--letter", help="cover letter Markdown source")
    ap.add_argument("--letter-pdf")
    ap.add_argument("--posting", help="posting text")
    ap.add_argument("--career", help="career.md, to trace numbers")
    ap.add_argument("--keyword", action="append", default=[])
    ap.add_argument("--max-pages", type=int, default=2)
    fails, reviews, passes = check(ap.parse_args(argv))
    for f in fails:
        print("FAIL   " + f)
    for r in reviews:
        print("REVIEW " + r)
    for p in passes:
        print("PASS   " + p)
    print(f"{len(fails)} fail, {len(reviews)} to review, {len(passes)} pass")
    return 1 if fails else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a code page that cannot print every character
        stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
