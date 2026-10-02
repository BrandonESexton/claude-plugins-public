---
name: update-tracker
description: >
  Use when the user wants to add or update a job in their application tracker sheet.
  Triggers on: "add this to the tracker", "update the tracker", "I submitted X", "I got a
  rejection from X", "recruiter call with X", "move X to interviewing", "I'm passing on X",
  or after build-application finishes. Adds a row, updates status, dates, ratings, or
  expectation, or logs a pass on the passed tab.
metadata:
  version: "0.2.0"
---

## Where

Google Sheet `tracker.sheet_id` from `~/.config/job-application/config.yaml` (see the `apply` skill for the missing-config interview). Use the Google Sheets tools (`get_values`, `append_values`, `update_values`). Column letters come from `tracker.columns`; status strings from `tracker.statuses`. Passed roles go on `tracker.passed_tab` as Company, Role, Why passed.

## Steps

1. **Read the sheet** (`<tab>!A1:Z500`) and find the company. Match on company and role. If the company exists with a different role, confirm whether it is a new row.
2. **Existing row:** update only the cells that changed (usually status, date, expectation, next step). Write exact cell ranges. Never overwrite a whole row.
3. **New row:** first empty row after the data. Write every known non-formula column. For columns marked formula in the config, check a neighboring row: if it holds a formula, copy the same pattern adjusted to the new row number; otherwise leave it and say so. Never hardcode a formula's result.
4. **Pass:** append to the passed tab only.
5. **Status rules.**
   - After a build with no submission confirmed: `statuses.built`.
   - Once the user says they submitted: `statuses.applied`, with the date.
   - Recruiter or interview news: `statuses.interviewing` (or `statuses.recruiter`), with the next step and its date in the next-step column.
   - Never mark applied or interviewing on a guess.
6. **Read back** the row after writing and confirm the values landed.
7. **Notes file.** If the status changed and `files.notes_dir/<company>-<role>-notes.md` exists, offer to update its status line.
8. **Hand off.** Moving to interviewing or logging a recruiter call: offer `interview-prep`. Marking applied: mention the first follow-up is due in `followup.applied_first_days` days.

## Rules

- Fill what is known; leave unknowns blank and say which.
- Ratings come from the review. Do not re-rate silently.
- Salary expectation only gets filled when the user reports what they entered or said.
- No em dashes in anything written to the sheet.
