---
name: backlog-grooming
description: >
  Grooms Backlog-status tickets in the configured Jira project into a standard 4-part
  description (who/what/why, Definition of Ready checklist, Definition of Done scaffold,
  Dependencies), assesses readiness, flags duplicates with a comment and issue link, and
  either moves ready tickets to To Do or asks the reporter for exactly what is missing. AI
  token or spend increase requests skip the rewrite and are checked against a simpler bar
  (approving manager set, real prompt evidence), with a prompt-efficiency review posted
  before they move. Trigger on "groom the backlog", "backlog grooming", "get the backlog
  ready for sprint planning", "DOR check", "definition of ready review", or any request to
  prep Backlog tickets before sprint planning. Do not trigger for Epics or tickets already
  past Backlog.
metadata:
  version: "1.2.0"
---

# Backlog Grooming

## Why this exists

Tickets were reaching sprint planning without enough content to act on: titles with no description, no acceptance criteria, unnamed dependencies. Grooming now happens up front. Every Backlog ticket gets the same 4-section structure, readiness is judged against a fixed checklist (not re-derived per ticket), and tickets that are not ready get a comment addressed to the reporter asking exactly what is missing.

`references/dor-dod-checklist.md` holds the checklist, the description template, and the comment templates. Reuse them verbatim.

## Config

Read `~/.config/jira-ops/config.yaml`. If missing, ask for the values in `config.example.yaml` in one short interview and write the file. All keys, IDs, and field names below come from config.

## Scope

```
project = <jira.project_key> AND issuetype != Epic AND status = Backlog
```

## Tool routing

If `connectors.prefer` is set, search that gateway's tools first for each Jira operation (search, edit, comment, link, transition), and fall back to the native Atlassian connector for anything it does not cover.

## Batching

Pull every matching issue in one paginated search with only: summary, description, story points, epic link, assignee, reporter, priority, comment, updated. Build a compact table before reading any description in full. Never re-fetch an issue already in the batch. Process in groups of 10 to 15.

If a configured field ID errors, look it up with a field-metadata call for the project instead of guessing, and offer to save it to config.

## Already-processed check (runs first)

This is what keeps a recurring run from posting the same comment over and over.

Every comment this skill posts ends with `grooming.signature`. Identify the skill's own earlier comments by that signature, not by comment author, because the person running the skill also leaves manual comments.

1. If the most recent comment carries the signature **and** the issue's `updated` time is not newer than that comment's `created` time, skip the ticket entirely. Report it as "no new activity since last comment."
2. Otherwise continue.
3. When re-evaluating a ticket that already has a signed comment and the result is still Not Ready (or still a duplicate, or the spend bar is still not met), compare the new gaps with what the last comment asked:
   - Same gaps: do not comment again. Report "still waiting on: <gaps>".
   - Gaps changed, or the ticket is now Ready: proceed normally.
   - Now Ready but the last comment asked something that no longer applies: post a short closing comment before moving it ("Following up: everything checks out, moving this to To Do"). Never leave a stale question as the last visible activity.

## Per-ticket procedure

0. **AI spend request check.** If this is an AI token, usage, or spend increase request (see below), skip to that section.
1. **Read the original description once.** If it already contains an earlier grooming pass, keep only the reporter's original text that precedes it (see the reference file).
2. **Epic assignment.** For Story, Task, Bug, and Initiative (not Sub-task or Spike), if the epic link is empty: pull the open epics in the project, match the ticket's ask against their themes by judgment, and set the best fit. If nothing fits, use `grooming.catch_all_epic`. Never ask the reporter, who has no view into the team's epic structure. Do this whether or not the ticket ends up Ready. Leave existing epic links alone.
3. **Draft the rewrite** into the 4-section template, preserving the verbatim original at the top. Draft only, no Jira call yet. Use the glyphs ✅, ☐, and N/A. Never markdown `- [ ]` checkboxes: Jira's markdown converter silently drops them.
4. **Duplicate check.** Compare against the rest of the batch plus a light text search (`project = <key> AND text ~ "<3-5 distinguishing words>"`, excluding this ticket). Judge overlap by eye: the same underlying ask, not shared generic words. When unsure, do not flag. Before linking, look up the exact link-type name (for example "Duplicate"); names vary by site. For a likely duplicate, post the duplicate comment on both tickets and link them. A duplicate flag blocks the move to To Do regardless of readiness, so two duplicates cannot both slip through in one run.
5. **Readiness verdict** against the 7-item checklist. "Sized to fit one story" is a real gate: scope over `jira.max_story_points` fails it.
   - **Ready:** one description edit with the groomed text, set story points. Then look up this issue's available transitions and pick the one whose target status is "To Do". Never reuse a transition ID seen on another issue; IDs differ by issue type and workflow. Skip the move if flagged duplicate, and report it.
   - **Not ready:** one description edit with gaps marked inline (for oversized scope, include the recommended split in one sentence), leave it in Backlog, and post the not-ready comment to the reporter listing only what is missing, as direct questions.

## AI spend increase requests

Simple asks, not stories. Skip the rewrite, the checklist, and the duplicate check. Do not touch the description.

**Parent:** set the ticket's parent to `ai_spend.requests_epic` as soon as it is detected, whether or not it ends up Ready. Skip if already set.

**Detection:** the summary or description is about increasing an AI token, usage, spend, credit, or seat limit, with increase language ("increase", "top up", "raise", "bump", "more"). A judgment call on wording, not a regex.

**Bar (both required):**
1. **Approving manager set**: the `jira.fields.approving_manager` field is filled. This checks that it is filled, not that the person is the reporter's actual manager.
2. **Real usage evidence**, either:
   - **Two example prompts** the requester uses regularly, in the description or a comment. Fewer than two, or a description of usage with no prompt text, does not count.
   - **A skill, provided in full** as an attachment or pasted content, when the requester says they use a skill instead of raw prompts. A skill named but not provided does not count.

**Ready:** run the prompt-efficiency review (`references/prompt-efficiency-review.md`) and post its comment. Only after that comment has posted: move the ticket to To Do the same way as above, and in the same batch of field writes set the assignee to `ai_spend.processor_account_id`, story points to `ai_spend.points`, and add it to the active sprint (look the sprint up live every run). If the review cannot be produced (unreadable attachment, nothing substantive to say), leave it in Backlog and report it.

**Not ready:** leave it in Backlog and post the matching missing-info comment from the reference files. Not the standard not-ready comment.

The actual limit change is a separate, human-run step: the `ai-spend-increase` skill.

## Skip entirely

- Restating why a good ticket is good.
- Re-deriving the checklist definitions per ticket.
- Quoting the full original back when nothing changed its meaning.

## Report

One line: `N processed (R moved to To Do, B left in Backlog, S skipped, no new activity)`, then bullets for only the notable findings: duplicates held for triage, tickets put in the catch-all epic (worth a human look), oversized or undersized tickets, tickets still waiting on the same gaps. No per-ticket recap; that is in Jira.

## Out of scope

- Sprint planning from To Do.
- Checking Definition of Done at completion; DoD here is a scaffold.
- Closing duplicates. Flag and link only; a human decides.
