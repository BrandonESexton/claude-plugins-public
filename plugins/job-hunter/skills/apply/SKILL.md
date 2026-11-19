---
name: apply
description: >
  Use after a go on a posting, or when the user says "apply to this", "build my resume for this job",
  "write the cover letter", or "/apply". Builds a tailored resume as a real .docx and PDF from the
  user's resume template, an optional cover letter, and a notes file with honest answers for the
  application form, checks everything with a verify script, and logs it in the tracker. Never submits.
---

Read `${CLAUDE_PLUGIN_ROOT}/RULES.md`, then `job-search/career.md`, `job-search/preferences.md`, and `${CLAUDE_PLUGIN_ROOT}/skills/resume-makeover/references/resume-standards.md`. If the posting has not been through `check-fit` in this conversation, run it first and wait for a go. Use its matrix, knock-out answers, gaps, keywords, and mirror risk.

**Template first.** If `job-search/resume/resume-template.md` and `resume-master.md` exist, start from the master and follow the template's section order and tailoring rules. If not, offer `resume-makeover` once (it pays off on every application); if the user declines, start from career.md and the standards file.

## Build (folder `job-search/applications/<company>-<title>-YYYY-MM-DD/`)

1. **resume.md**, in the Markdown the renderer reads (see the top of `scripts/render.py`: `# Name`, contact lines, `## Section`, `### Title, Employer | Dates`, `- bullet`).
   - **Title line and summary:** the posting's job title as written (no location or "Remote" tag), then what the user is best at for this job. The top third must pass the six-second test: target role, strongest matching proof, one real result.
   - **Bullets:** reorder and reword toward the `critical` and `high` rows. Action + what + how + number + outcome. Vary the opening verbs.
   - **Keywords, not copying.** Use each keyword from `check-fit` once, in context, where career.md backs it. Write every bullet around what the user did, in their words. Never copy 8 or more words in a row from the posting, and use the posting's headings as at most one skill label. If mirror risk was High, paraphrase the named passages harder.
   - **Repetition:** each headline number appears at most twice on the resume.
   - **Calibration:** never stronger than career.md. "Used" never becomes "built"; Working and Exposure skills are never "expert" (RULES.md #3). A "no" from `check-fit` is a gap, not a keyword.
   - **Length:** let the content decide. One page for most people under about 10 years, two pages is fine when the experience is there. Never three.
2. **cover-letter.md**: optional. Default to writing one for small employers, career changers, relocation, or when the posting asks for one; otherwise ask the user whether they want one. Under 250 words. The opening names the job and one concrete reason they fit; one short quoted line from the posting is allowed there. The middle gives two proof points from career.md tied to the top needs. A short close.
   - **Gaps:** for a field change, one honest sentence about the switch. For a missing tool or skill, say nothing about it; write about the closest real experience instead. Never apologize or hedge.
   - Write in the user's voice from their own answers. No stock phrases, no em dashes.
3. **notes.md**: posting link and pay, fit and flags from the review, the **form answers** (years of experience to type, licenses, work authorization, education, salary expectation using their target and the posting band, start date, why this employer, why leaving), a **gap list with one interview talking point each** (never in the letter), and anything the user must do or check themselves. Flag every answer left blank.

## Render and verify

1. Render: `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/render.py" resume.md --out <folder> --name <First_Last>_Resume_<Company>`, and the same for the letter with `_Cover_Letter_<Company>`. It writes a one-column .docx and a text-based PDF and prints the page count.
2. Verify:
   ```
   <python> "${CLAUDE_PLUGIN_ROOT}/scripts/verify.py" --resume resume.md \
     --docx <resume.docx> --pdf <resume.pdf> --letter cover-letter.md --letter-pdf <letter.pdf> \
     --posting <saved posting .txt> --career job-search/career.md --keyword "<each keyword>"
   ```
   Drop the letter flags if there is no letter. Exit 1 means a FAIL. Fix the Markdown, re-render, rerun, at most 3 rounds. An `untraced number` means the number is not in career.md: trace it to the user's answer, or remove it. Never add a keyword to pass coverage if career.md does not back it.
3. If Python is not available, say so, keep the Markdown files, and do the same checks by reading (RULES.md #8). Do not skip the check silently.

## Hand off

Show a short report: pages, what verify fixed, keyword coverage, and anything left for the user to decide. Then the file paths. Tell them to read every line, change anything that does not sound like them, and submit on the employer's own site (better than an "easy apply" button, which often auto-rejects on screening questions). Never click Apply or send anything.

When they say they submitted, get the row id with `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" seen --company "<c>" --title "<t>" --location "<l>"`, then `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" update <id> --status applied --followup <date one week out>`. Interview: run `interview-prep`. Offer: run `evaluate-offer`. Silence after a week: run `follow-up`.
