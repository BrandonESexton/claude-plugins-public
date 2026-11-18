# job-search-starter

A guided job search for any field. Built for someone who is new to using AI for this and does not know where to start.

## Install (Claude Cowork)

1. Zip the `job-search-starter` folder (the `.claude-plugin` folder must be at the top of the zip).
2. In Claude Cowork, upload the zip as a plugin and accept it.
3. Pick (or create) an empty folder for the job search when Cowork asks which folder to work in.

## Use

Say `/job-search-starter:start` (or just "help me find a job").


| Skill | What it does |
| --- | --- |
| `start` | Onboarding. Takes a resume, reads it, interviews you, and writes `career.md` and `preferences.md` (target role, pay, location, dealbreakers, where to look). |
| `scan` | Searches the boards you chose, filters by your preferences, and writes a ranked report. Run weekly. |
| `review-posting` | Paste a posting. Get an honest fit review against your career file and pay floor, then a go or no-go. |
| `status` | Where things stand and what to do today: pipeline, follow-ups due, one honest coaching note. |
| `apply` | After a go. Builds a tailored resume and cover letter, notes for the application form, and logs it in the tracker. You submit it yourself. |
| `interview-prep` | Company brief, story map from your career file, likely and hard questions, and a practice round with feedback. |
| `follow-up` | Drafts follow-ups, thank-you notes, and replies. Never sends. |
| `offer` | Checks an offer against your floor, target, benefits and the market, and drafts a negotiation script. |

## Files it creates (all in `job-search/`)

```
career.md            what you have done, with numbers
preferences.md       what you want, pay, dealbreakers, boards
tracker.csv          every job you looked at or applied to (managed by scripts/tracker.py)
scans/               one report per scan
applications/        one folder per application (resume, cover letter, notes)
```

## Tests

```
python3 -m unittest discover -s tests
```

## Limits

- The tracker script needs Python 3 in Cowork's environment. If it is not there, the plugin silently falls back to a plain list. Untested in Cowork so far.

- It never submits an application or sends a message. You do.
- Scans use whatever web or browser tool Claude has in your setup. If it cannot open a job board that needs a login, it says so and falls back to web search.
- Pay research is a market estimate from public postings, not a promise.
