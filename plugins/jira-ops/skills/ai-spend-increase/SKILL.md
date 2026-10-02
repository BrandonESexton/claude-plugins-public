---
name: ai-spend-increase
description: >
  Processes one AI spend-limit increase for one Jira ticket already parented to the
  configured requests epic. Pulls the reporter, checks their current limit and
  month-to-date spend with the spend admin tool, says exactly who it is checking, and asks
  the operator what to set the limit to. On a decline, stops with no changes. On a target
  amount, previews then applies it, comments the old and new limit on the ticket, and moves
  the ticket to Done. Trigger on "process OPS-1234 for spending", "process the spend
  increase for OPS-1234", or any phrasing pairing a ticket key with a spend or limit word.
  Do not trigger for batch processing or for re-checking the grooming bar.
metadata:
  version: "1.0.0"
---

# AI Spend Increase

## Why this exists

`backlog-grooming` checks spend requests against a bar and posts an efficiency review, but never changes an actual limit. Changing a limit moves real money and access, so it should not run unattended inside a sweep. This is the second, human-in-the-loop step: one ticket, check the current limit, ask the operator, apply, record.

## Config and tools

- `~/.config/jira-ops/config.yaml` (missing-config interview as in `backlog-grooming`).
- **Spend admin tool**: an MCP server or connector for your AI platform's admin API that exposes (names will vary): `get_user_spend_limit(user)` returning the effective limit and month-to-date spend, and `set_user_spend_limit(user, amount_usd, confirm)` where `confirm=false` previews and `confirm=true` applies. If no such tool is connected, say so and stop. This skill never edits limits any other way.
- Jira operations: `connectors.prefer` first if set, else the native Atlassian connector.

## Procedure

1. **Fetch and gate.** Pull the ticket. If its parent is not `ai_spend.requests_epic`, stop and say why.
2. **Name the requester.** Get the reporter's display name and email and say it before anything else: "Checking spend limit for **{name}** ({email})." This is the checkpoint where the operator can catch a ticket filed on someone else's behalf. If they name a different person, use that person from here on.
3. **Check the current limit.** `get_user_spend_limit(email)`. Report the effective limit and month-to-date spend in plain text.
4. **Ask.** "Raise it? What should it be?" An open-ended absolute amount, never a delta, never multiple choice.
5. **Decline.** On no, skip, or hold: stop. No comment, no write, no status change.
6. **Apply.** `set_user_spend_limit(email, X, confirm=false)` to preview, then `confirm=true` to apply. The amount given in step 4 is the approval; do not ask again.
7. **Record.** Only after a confirmed successful write, comment:

   ```
   AI spend limit updated for {name}: from ${old} to ${new}/month for {Month YYYY}.

   _Posted by ai-spend-increase._
   ```

   The literal old and new values make the direction obvious; no special wording for a lower or unchanged limit.
8. **Close.** Look up this ticket's available transitions; never reuse an ID from another ticket. Match the status **name** "Done", not the status category, because a status like "Canceled" shares the done category. If no transition reaches Done directly, take the one that moves forward through the workflow (toward In Progress), re-fetch, and repeat. If nothing makes forward progress, stop and report the current status and the available transitions.
9. **Report.** One line: old limit to new limit, ticket Done.

## Errors

- **Wrong parent:** stop after step 1.
- **No email, or user not found by the spend tool:** report it and ask for the right email or user ID. Never guess.
- **Apply fails:** report the error verbatim. No comment, no transition.
- **Stuck transition:** stop after step 8 and report. Steps 6 and 7 have already happened; only the status change is stuck.

## Out of scope

- Batch processing.
- Re-verifying the approving manager or usage evidence.
- Org-wide spend reporting.
