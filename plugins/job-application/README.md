# job-application

Six skills that run a job search from first read to follow-up, built around one rule: nothing goes on a resume, in a letter, or into an interview answer that your own facts file does not support.

| Skill | What it does |
|---|---|
| `apply` | Entry point. Review, wait for your go/no-go, build, record. |
| `review-posting` | Honest fit read: liveness and staffing-agency checks, a two-pass requirement matrix against your facts file, fit 1-5, career impact 1-5, comp vs your floor with a reliability read, posting legitimacy, level strategy, gaps with mitigations, keywords to mirror. |
| `build-application` | Builds the resume, cover letter, and notes file from your templates, then checks the six-second read, your claim rules, banned phrasing, and keyword coverage. |
| `update-tracker` | Adds or updates the row in a Google Sheet tracker. Passes go on their own tab. |
| `interview-prep` | Researches the process, maps rounds to audiences, lists likely questions with answer outlines, matches them to a STAR+R story bank, and debriefs afterward. |
| `followup` | Shows what is due, drafts follow-ups and thank-yous, finds a hiring manager or recruiter and drafts a LinkedIn note. Never sends. |

See [examples/sample-review.md](examples/sample-review.md) for what a review looks like (fictional company and candidate).

## Setup

1. Copy `config.example.yaml` to `~/.config/job-application/config.yaml` and fill it in. If you skip this, the first run asks for the values and writes the file.
2. Write your facts file (`candidate.facts_file`): roles, dates, scope, real numbers, tools, and anything you will not claim. This is the most important input. The better it is, the better everything else gets.
3. Put your hard "never claim this" rules in `claim_rules`. The build skill checks every resume and letter against them.
4. Templates: two scripts that write a .docx to the path given as their only argument. Content in constants at the top, styling below.

## Needs

Google Sheets connector, web search, and on the machine that builds documents: Node, LibreOffice, and poppler (`pdfinfo`, `pdftotext`). Gmail connector is optional (follow-up drafts).

## Use

- `/apply <posting URL or pasted text>`, or paste a posting and ask "should I apply to this".
- "Review this posting" for the read only.
- "Prep me for the X interview" / "debrief my X interview".
- "Any follow-ups due?" / "find the hiring manager at X".

## Why it works the way it does

- **Importance before match.** Requirements are rated from the posting alone before your background is read. Rating after seeing a match biases toward your strengths and hides real gaps.
- **Guesses cannot become must-haves.** An importance rating based on market knowledge rather than the posting's own words can never be `critical` or `high`, because those ratings trigger interview-prep work and can talk you out of applying.
- **Legitimacy is separate from fit.** A great-fit ghost posting is still a waste of an afternoon, and a thin posting is not automatically fake. They are scored separately.
- **Gaps are named, not hidden.** Each important gap gets an interview risk and a mitigation, and the cover letter says it plainly. Recruiters find gaps anyway; naming them first reads as senior.
- **Nothing sends itself.** Every email, note, and submission is yours to send.

Ideas adapted from [career-ops](https://github.com/career-ops-hq/career-ops) (MIT).
