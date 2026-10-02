---
name: build-application
description: >
  Use when the user has decided to apply and wants the materials built. Triggers on: "build
  the resume and cover letter", "go ahead and build it", "make the application for X",
  "tailor my resume for this", "write the cover letter". Builds the tailored resume, cover
  letter, and per-company notes file from the user's templates, then checks the result for
  recruiter clarity, posting keyword coverage, claim rules, and banned phrasing.
metadata:
  version: "0.2.0"
---

## Read first, every time

- `~/.config/job-application/config.yaml` (see the `apply` skill for the missing-config interview).
- `candidate.facts_file`: nothing goes in a resume or letter that this file does not support.
- `candidate.standards_file` if set. If it disagrees with the template code, the template wins.
- One or two recent notes files for similar roles in `files.notes_dir`, to match framing and gap wording the user already approved.

Needs the fit review first. If there is none in the conversation, run `review-posting`. Pull from it: the requirement matrix, the gaps and mitigations, the strengths to lead with, and the keywords to mirror.

## Template contract

`files.resume_template` and `files.cover_letter_template` are scripts that write a .docx to the path given as their only argument (for example, Node scripts using the `docx` package). Content lives in plain constants near the top; styling and helpers below. Requires Node, LibreOffice (`soffice`), and poppler (`pdfinfo`, `pdftotext`). If a command is missing, say so instead of working around it.

## Plan before writing

Build a short risk map for yourself (do not print it unless asked): the doubts a recruiter will have, and the fact that answers each.

| Doubt | Answer from the facts file | Where it goes |
|---|---|---|
| Can they run this stack? | matching tools in real context | competencies, first bullets |
| Are they senior enough? | scope, team, decisions owned | stat bar, summary |
| Is the domain close? | similar scale, users, constraints | summary, letter |
| Is this generic? | role-specific problems from the posting | title line, letter opening |

Never invent evidence to close a doubt. An unanswered doubt is a gap and goes in the letter's gap paragraph.

## Build

1. **Copy the templates** to `<template dir>/resume_<company>.js` and `cover_letter_<company>.js` (lowercase, underscores). Never edit the templates themselves. If the company file exists, ask before overwriting.
2. **Change content only.** Styling constants and helpers stay untouched. Edit with a short read-modify-write script, not by retyping the file.
   - Title line: the posting's exact title, then ` | ` and two or three focus areas.
   - Stat bar: 4 or 5 proof points tailored to the posting.
   - Summary, competencies (ordered by the matrix importance bands), and bullets reordered or reworded toward the posting.
   - **Six-second test.** The title line, stat bar, and summary alone must make the fit obvious: target role, strongest matching stack or domain, and one real outcome. If a recruiter would have to dig to see the fit, rework the top third.
   - **Bullets.** Shape: action + system or scope + tool or approach + outcome. Vary the opening verbs. Never "helped", "assisted", "responsible for", "worked on", or "participated in" when the candidate owned the work.
   - **Keywords.** Work the review's keywords in where the facts file backs them, in real context. Reword and reorder, never fabricate. A tool used is never a tool built.
3. **Cover letter.** Salutation to the hiring team (a name if known). Quote or reference one specific line from the posting. Map two or three real stories to the `critical` and `high` requirements. Include a paragraph that names real gaps plainly, from the review's gaps and mitigations, unless the user says to leave it out.
4. **Run the builds**: `node resume_<company>.js <files.resume_out_dir>/<Name>_Resume_<Company>.docx`, same for the letter into `files.cover_letter_out_dir`.
5. **Convert to PDF**: `soffice --headless --convert-to pdf --outdir <same folder> <file.docx>`.
6. **Verify layout.** Page counts must equal `files.resume_pages` and `files.cover_letter_pages` (`pdfinfo`). Render pages to images and look if a viewer is available; nothing orphaned at the top of a page. If a count is off, tighten wording. Never shrink fonts or margins.
7. **Rule check.** Pull the text from both PDFs with `pdftotext` and check. Fix and rebuild before delivering.
   - No em dashes.
   - Every rule in `claim_rules`. A plain text search often hits allowed uses (a tool named under an earlier employer), so read each hit in context and flag only real violations.
   - Title line matches the posting title word for word.
   - Banned phrasing, case-insensitive, whole words only (pdftotext can drop hyphens at line breaks, so "peer-facilitated" may show up as "peerfacilitated"; that is not a hit): "passionate about", "results-oriented", "proven track record", "leveraged", "spearheaded", "facilitated", "synergies", "robust", "seamless", "cutting-edge", "innovative", "best practices", "demonstrated ability", "I am writing to express", "fast-paced", plus `style.banned_phrases`.
   - The same verb opening three or more bullets in a row.
8. **Keyword coverage.** Check each review keyword against the resume text and report covered and missing. For each missing one: if the facts file backs it, add it in real context and rebuild; if not, leave it out, and make sure the letter's gap paragraph covers it when it is `critical` or `high`. Never add a keyword just to raise coverage.
9. **Notes file.** Write `files.notes_dir/<company>-<role>-notes.md`: header (posting URL, job ID, apply portal, posted comp), fit read (scores, legitimacy, requirement matrix), framing used, gaps named in the letter, keywords mirrored and any left out on purpose, open items (salary question, uploads, contacts), files built, status.
10. **Companion files.** If the process asks for more (exercise, portfolio, application questions), build those too. Ask if the ask is unclear.

## Deliver

Folder and file names, page counts, the keyword coverage line, and what the user must do themselves (submit, salary field, uploads). Do not paste the full contents. Then hand off to `update-tracker`.

## Rules

- Do not invent experience, numbers, or tools. A missing requirement goes in the gap paragraph, not the resume.
- Do not change older resumes. Only create new files.
- If `style.voice_skill` is set, run the cover letter through it before the final build.
