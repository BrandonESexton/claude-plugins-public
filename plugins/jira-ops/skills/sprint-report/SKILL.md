---
name: sprint-report
description: >
  Pulls the active sprint for the configured Jira project and reports completed, in-flight,
  and not-started work, a per-person points table compared with each person's own
  historical average, whether each person's stated sprint goal has visible ticket work
  behind it, and process flags (missing points, stale or low-quality comments, thin
  descriptions, missing architecture sign-off). Also answers narrower workload questions
  ("is anyone overloaded") with a cheaper pull, and can write a closed sprint's final
  numbers to the velocity file on request. Trigger on sprint reports, sprint status, "did
  we hit our sprint goals", or workload and capacity checks for the team.
metadata:
  version: "1.1.0"
---

# Sprint Report

## Why this exists, and what it learned

Pulling sprint data from Jira without a plan is expensive: the API returns verbose objects (avatar URLs, schema metadata) even for simple field requests. An unguided first run took about 330K tokens and 57 tool calls. Batching, trimming fields, and triaging which comments to fetch brought it down sharply. The rest of this file is the plan that does that, plus fixes for real errors found along the way.

Running the full report for a narrow question ("is anyone overloaded") costs several times more than needed. Depth should match the question.

## Config

`~/.config/jira-ops/config.yaml` (missing-config interview as in `backlog-grooming`). Project key, field IDs, people, goals file, and velocity file all come from config. If a field ID errors, look it up with a field-metadata call and offer to save it.

Jira operations: `connectors.prefer` first if set, else the native Atlassian connector. Verify actual tool names on first use rather than assuming them.

## Step 0: pick the mode

- **Mode A, full report.** Sprint report, rundown, status, done/in-flight/not-started, sprint goals.
- **Mode B, workload only.** Overloaded, capacity, who has room. Points and completion per person against their own baseline. No comments, no description checks, no goal matching: those are the biggest cost and not what was asked.

Unsure: Mode A. Both modes paginate the whole sprint. "Lighter" means fewer fields, never stopping pagination early. An undercounted sprint produces a wrong workload table.

## Two traps to avoid every run

**Resolve the active sprint explicitly.** `sprint in openSprints()` matches active **and** future sprints, so it silently pulls in tickets already planned into next sprint and inflates whoever has next-sprint work assigned. First run a 1-result lookup (`ORDER BY key DESC`, sprint field only) to get the current sprint's ID and confirm its state is `active`, then filter every query with `sprint = <id>`. Cross-check the sprint name against the goals file's "Current Sprint" heading; if they disagree, stop and flag it.

**Exclude Sub-tasks from every point sum.** Jira's own rollup counts only top-level Story and Task points; sub-task points are a breakdown of the parent's estimate. Summing every issue double-counts any story split into pointed sub-tasks. (On a real team this inflated one person's total by more than half.) Always request `issuetype` and drop sub-tasks before summing. Sub-tasks still appear in the done/in-flight/not-started lists; they just do not count toward points.

## Baselines: read them live

Do not hardcode a team or per-person target. A hardcoded number drifted far from reality within a few months. Read the velocity file's averages table every run and compare each person with **their own** average. A flat bar either flags a lower-throughput person every sprint or lets a higher-throughput person coast. Report the team total as a secondary momentum signal, not an accountability bar. If the velocity file notes an open caveat, mention it. A person with no history yet gets "no history yet", never someone else's average or zero.

People listed in config whose tickets are unpointed get a normal missing-points flag. Call out anyone with zero pointed tickets this sprint.

## Mode B

1. Resolve the sprint ID, then search `project = <key> AND sprint = <id>` with only status, resolution, assignee, story points, issuetype. Page size 6 to 8, paginate fully.
2. Drop sub-tasks, bucket by status category, sum points per person per bucket.
3. Compare each total with that person's average.
4. No comments.
5. Report: one line naming who is below their own baseline and who has room, a table (tickets, done, in progress, to do, total, rough hours remaining using `hours_per_point`), and 2 or 3 sentences of reasoning. Under 300 words.

## Mode A: pulling efficiently

1. **Bulk pass.** Resolve the sprint ID, then request summary, status, resolution, assignee, story points, description, labels, architecture approver, updated, issuetype. Page size 6 to 8, paginate to the end.
2. **Use `resolution`** to separate real Done from Canceled or Won't Do. **Use `issuetype`** to exclude sub-tasks from sums.
3. **Comments, triaged.** Only for in-progress tickets that are either updated 3+ days ago (staleness needs checking anyway) or worth 5+ points (the biggest work deserves a quality read). Fetch one ticket at a time; batching large comment threads blows response limits. Skip small, recently updated tickets on purpose, and report how many were skipped.
4. **For fetched comments, check two things:** staleness (days since last comment) and quality (does it explain progress or blockers, or is it "wip", "on it", a bare status echo). Flag them separately; a fresh comment can still be useless.
5. **Architecture sign-off.** Read the configured field; empty means no sign-off. Only flag tickets updated on or after `architecture_approver_since`, so old tickets do not create backfill noise.
6. **System-build classification.** Prefer a `system-build` label if present. Otherwise judge from summary and description using `system_build_keywords`, and say judgment was used.
7. **Optional, low priority:** a ticket that clearly produced a diagram or document with nothing attached or linked.

## Goal attendance

Both halves of this, matching and pace, are easy to get wrong, so the rules are stricter than instinct.

1. Read the goals file's "Current Sprint" section and confirm the sprint name matches.
2. **Match in two tiers and label every match.**
   - **Tier 1, explicit keys.** Pull every ticket key from the goal text and check each against that person's tickets this sprint. Confirmed matches. If a named ticket is not theirs this sprint (reassigned, moved, wrong key), say so.
   - **Tier 2, inferred.** Only for parts of a goal with no ticket key. Report the candidate ticket and a one-line reason, tagged "inferred". If nothing clears a reasonable bar, report "no ticket work found" rather than force a weak match.
3. **Primary flag:** a goal, or part of one, with no ticket work behind it at all. This matters more than pace.
4. **Pace note only on real signal:** the goal states a concrete deadline, or every matched ticket has points and an open status. Base it on the matched tickets' remaining points vs days left, not the person's total load. Otherwise write "not enough signal for a pace read". A stated "no read" beats a fabricated one.

## Mode A report

Under about 800 words. No raw JSON, no dumped URLs.

1. **Sprint health in one line:** issue count, end date, completion %, with canceled or descoped called out separately from done.
2. **Completed / In flight / Not started** by person, short bullets.
3. **Per-person table:** Person | Tickets | Done | In progress | To do | Total | vs own average | Rough hours remaining. Points exclude sub-tasks.
4. **Goal attendance**, one line per person: goal, matched tickets tagged confirmed or inferred or "no ticket work found", and a pace note only when there was signal.
5. **Flags:** missing points, stale comments (ticket and days silent), low-quality comments, thin descriptions, system-build tickets missing sign-off, someone notably below their own average, and lower priority missing artifacts. Include the count of tickets skipped by comment triage.

If a response-size limit still hits, say so in passing and drop the page size further instead of retrying the same call.

## Closing a sprint into the velocity file

Only on explicit request ("close out this sprint", "add this sprint to the velocity tracker"), never as a side effect of a mid-sprint report.

1. If a column for this sprint exists (for example marked in progress), update it in place. Add a column only when the sprint is not there yet.
2. Credit a ticket to the sprint whose date range contains its resolution date, not every sprint it touched (carryover would otherwise count twice).
3. Recompute the team total and the averages.
4. Update the "Last updated" line and mark the figures final.
