---
name: apply
description: >
  Use after a go on a posting, or when the user says "apply to this", "build my resume for this job",
  "write the cover letter", or "/apply". Builds a tailored resume and cover letter, a notes file with
  answers for the application form, and logs it in the tracker. Never submits.
---

Read `${CLAUDE_PLUGIN_ROOT}/RULES.md`, then `job-search/career.md` and `job-search/preferences.md`. If the posting has not been reviewed, run `review-posting` first and wait for a go.

## Build (folder `job-search/applications/<company>-<title>-YYYY-MM-DD/`)

1. **resume.md** (and a .docx if a docx tool is available, since most employers want Word or PDF): one page for under 10 years of experience, two otherwise. Lead with the strongest match to this posting. Mirror the posting's own words for skills he truly has. Use accomplishment bullets with numbers from career.md. Drop what does not help. Never add a skill, title, date, number, or credential not in career.md. Plain formatting with no tables, columns, or images, so applicant systems can read it.
2. **cover-letter.md**: under 250 words. Opening names the job and one concrete reason he fits. Middle gives two proof points from career.md tied to the posting's top needs. Close is short. If there is a gap (field change, missing credential), address it in one honest sentence. Write in his voice from his own answers; no stock phrases ("passionate", "excited to leverage", "I am writing to apply"), no em dashes.
3. **notes.md**: the posting link, pay and fit from the review, answers to likely form questions (why this company, why leaving, salary expectation using his target and the posting band, start date, work authorization if he told you, references if he gave them), and anything he must do or verify himself. Flag every answer you had to leave blank for him.

## Check, then hand off

Re-read the resume and letter against career.md. List any line you cannot trace and fix or remove it. Show him a short summary and the file paths. Tell him: review it, edit anything that does not sound like him, and submit it himself on the employer's site. Never click Apply or send anything.

When he says he submitted, get the row id with `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" seen --company "<c>" --title "<t>" --location "<l>"` (prints the id), then run `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" update <id> --status applied --followup <date one week out>`. If he gets an interview, run `interview-prep`. If he gets an offer, run `offer`. For silence after a week, run `follow-up`.
