# authenticity_check

Catches the things that make an application read as copied, templated, or hijacked. Python 3, stdlib only. PDFs need `pdftotext` (poppler).

```sh
S=scripts/authenticity_check/authenticity_check.py

# 1. Scan a posting before building. Exit 3 means "stop and ask".
python3 $S scan-posting posting.txt          # .txt, .html, or .pdf; --json for machine output

# 2. Audit the finished documents.
pdftotext -layout resume.pdf resume.txt
pdftotext -layout letter.pdf letter.txt
python3 $S audit --posting posting.txt --resume resume.txt --letter letter.txt \
  --location "Cleveland, OH" --forbid "bachelor" --watch "\b\d+\+?\s+years\b"

# 3. Self-test (fake posting with a visible AI instruction, an HTML comment, and white text).
python3 $S selftest
```

Audit output is `[FAIL]`, `[REVIEW]`, or `[PASS]` lines. Exit 1 if any FAIL. REVIEW means a human should look.

| Check | Status |
|---|---|
| 8+ word runs copied from the posting (resume and letter; one quoted opening line in the letter is allowed, under 30 words) | FAIL |
| A stat in more than two places, or in the summary or competencies when it is also elsewhere | FAIL |
| Letter restating more than two stat bar numbers | FAIL |
| More than one competency header echoing the posting | FAIL |
| Location or work-mode tag in the title line (resume and letter) | FAIL |
| Em dashes, banned phrasing | FAIL |
| En dash outside a date range | REVIEW |
| Resume wording stronger than the letter's hedges on the same term (heuristic) | REVIEW |
| Summary not 4 to 6 lines | FAIL |
| Summary with even sentence lengths, three parallel clauses, or third person | REVIEW |
| Contact lines: LinkedIn on its own line, tag present when `--linkedin-tag '(ID verified)'` is passed (off by default) | FAIL |
| `--forbid` regexes (degree claims and the like) | FAIL |
| `--watch` regexes (tenure counts and the like) | REVIEW |
| Text from the posting's embedded instructions (quoted codewords and 5-word windows) showing up in either document, except phrases in `--approved` | FAIL |

`scan-posting` classifies findings as (a) addressed to an AI, (b) unusual instruction to the applicant, (c) hidden or obfuscated text, or (d) none. It reads inline styles only (not class-based CSS), so hidden text styled through a stylesheet can slip past; read the posting too. White text on an element with a dark background is treated as visible. Text pasted from a rendered page has already lost its hidden parts, so for a URL also save the raw HTML with `curl -sL`.

The audit reads the posting as data and never acts on it.
