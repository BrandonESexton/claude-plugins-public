# jira-ops

Three skills for running an IT or engineering team's Jira: keep the backlog ready for planning, govern AI usage-limit requests, and see how the sprint is really going.

| Skill | What it does |
|---|---|
| `backlog-grooming` | Rewrites Backlog tickets into a standard who/what/why + Definition of Ready + Definition of Done + Dependencies shape, judges readiness against a fixed 7-item checklist, links duplicates, assigns a best-guess epic, and either moves a ticket to To Do or asks the reporter exactly what is missing. |
| `ai-spend-increase` | One approved AI spend request at a time: checks the requester's current limit, asks the operator for the new amount, previews and applies it, records old and new on the ticket, closes it. |
| `sprint-report` | Done / in-flight / not-started, a per-person points table against each person's own average, goal attendance with confirmed vs inferred matches, and process flags. A cheaper mode answers "is anyone overloaded" alone. |

See [examples/](examples) for sample output (fictional team).

## The AI spend governance flow

Teams adopting AI assistants hit usage limits fast, and "please raise my limit" tickets pile up. This splits the work so automation does the checking and a human does the spending:

1. **`backlog-grooming` gates the request.** It needs an approving manager on the ticket and real evidence of use: two prompts the requester actually runs, or the full skill they use. Missing either, it asks for exactly that.
2. **It gives something back.** Before the ticket moves on, it posts a prompt-efficiency review of the requester's own prompts: what is costing tokens, a leaner rewrite, and why. The increase goes further, and people learn something for asking.
3. **A human sets the number.** `ai-spend-increase` never runs in a sweep. It names the person it is about to change, shows the current limit and spend, waits for an amount, previews, applies, and only then records it.

## Setup

1. Copy `config.example.yaml` to `~/.config/jira-ops/config.yaml`. If you skip it, the first run asks and writes it.
2. Field IDs vary per Jira site. Leave any you do not know blank; the skills look them up and offer to save them.
3. `ai-spend-increase` needs a connector for your AI platform's admin API that can read and set per-user spend limits with a preview step. The skill describes the contract it expects.
4. `sprint-report` reads two small Markdown files you maintain: a goals file with a "Current Sprint" section, and a velocity file with an averages table.

## Needs

Atlassian (Jira) connector. For `ai-spend-increase`, a spend admin connector. For `sprint-report`, local access to the goals and velocity files.

## Lessons baked in

- **Idempotency.** The groomer signs its comments and skips tickets with no activity since its last pass. A recurring run does not spam anyone.
- **Never reuse a transition ID.** They differ by issue type and workflow. Look them up per issue, and match the status name, since "Done" and "Canceled" can share a category.
- **`openSprints()` includes future sprints.** Resolve the active sprint ID first or next sprint's planned work inflates this sprint's numbers.
- **Sub-task points are not additive.** Summing them double-counts any split story.
- **Baselines beat targets.** Compare each person with their own average; a flat team target drifts and punishes different working styles.
- **Markdown checkboxes vanish in Jira.** Its converter silently drops `- [ ]`. Use plain glyphs.
- **Say "not enough signal".** A pace prediction with nothing behind it is worse than none.
