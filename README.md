# Claude plugins for IT and engineering leaders

Four Claude plugins I built and used day to day: running a job search, grooming a Jira backlog and governing AI spend, triaging what needs me across email, Slack and Jira, and turning meeting transcripts into notes and action items.

They are written as Claude skills (Markdown instructions plus a small config file), so they run in Claude Code or Claude Cowork without any code to deploy.

| Plugin | What it does |
|---|---|
| [job-application](plugins/job-application) | Reviews a posting with an honest fit read, builds the tailored resume and cover letter, tracks the application, preps interviews, and handles follow-ups. |
| [jira-ops](plugins/jira-ops) | Grooms backlog tickets against a Definition of Ready, gates AI token-increase requests on evidence and a prompt-efficiency review, applies approved spend changes with a human in the loop, and reports sprint health against each person's own baseline. |
| [catch-me-up](plugins/catch-me-up) | One pass over Gmail, Slack, Jira, and other connected apps that reports only what actually needs you, sorted Critical or Important. Per-person setup. |
| [transcript-processor](plugins/transcript-processor) | Takes a meeting transcript, routes it to the right 1:1 or team file, writes the summary and action items, and flags issues showing up across more than one person. |

## Design choices that run through all of them

These matter more than the prompts themselves, and they came from things going wrong in real use.

- **A human owns every irreversible step.** Nothing sends an email, posts to Slack, submits an application, or changes a spend limit without an explicit go. Drafts are drafts.
- **Outside content is data, never instructions.** Job postings, emails, tickets, and transcripts can contain text aimed at an AI ("rank this highly", "forward this"). Every skill treats it as content to summarize and flags it rather than obeying it.
- **No invented facts.** Resume and interview content traces to one facts file the user owns. Questions inferred from a posting are labeled as inferred. A tool the user used never becomes a tool they built.
- **Judgment order is deliberate.** The job review rates how much each requirement matters from the posting alone, before reading the candidate's background, because rating importance after seeing a match biases it toward the candidate's strengths.
- **Idempotent automation.** The backlog groomer signs its own comments and skips tickets with no new activity since its last pass, so a recurring run never spams the same ticket.
- **Never trust a cached ID.** Jira transition IDs differ by issue type and workflow, and `openSprints()` matches future sprints as well as the active one. The skills look these up live each run.
- **Cost is a feature.** The sprint report started as a ~330K-token, 57-call run. Batching, field trimming, and a cheaper mode for narrow questions brought it down sharply. Depth matches the question.
- **Honest output beats a full report.** Empty sections are omitted, not padded. "Not enough signal" is a valid answer and beats a fabricated one.

## Install

Claude Code:

```
/plugin marketplace add BrandonESexton/claude-plugins-public
/plugin install job-application@claude-plugins-public
```

Claude Cowork: zip a plugin folder (for example `plugins/job-application`) and upload it.

## Configuration

Skills are plain Markdown, so there are no install-time variables. Each plugin ships a `config.example.yaml`. Copy it to `~/.config/<plugin-name>/config.yaml` and fill it in. Every skill reads that file at the start of a run, and if it is missing, runs a short setup interview and writes it for you. Nothing personal lives in the skill files.

`catch-me-up` keeps its settings in Claude's memory instead, so each teammate gets their own.

## Requirements

Depends on the plugin. Typical: Jira (Atlassian connector), Google Sheets, Gmail, Slack, web search. `job-application` also needs Node, LibreOffice, and poppler on the machine that builds documents. Each plugin README lists what it uses.

## Credits

Several ideas in `job-application` (the two-pass requirement matrix, posting legitimacy check, comp reliability read, recruiter risk map, STAR+R story bank, follow-up cadence) are adapted from [career-ops](https://github.com/career-ops-hq/career-ops) (MIT).

## License

MIT
