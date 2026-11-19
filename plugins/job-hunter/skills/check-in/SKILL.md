---
name: check-in
description: >
  Use when the user asks where things stand or what to do next. Triggers on: "/check-in", "where am I",
  "what should I do today", "how is my search going", "what is next". Reads the tracker, shows the
  pipeline, flags follow-ups that are due, and gives a short prioritized plan for today.
---

Read `${CLAUDE_PLUGIN_ROOT}/RULES.md`. If `job-search/preferences.md` is missing, run `setup`.

1. Run these three: `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" summary`, `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" due`, and `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" list`.
2. Show the pipeline in one line (found, reviewed, applied, interviewing, offer) and the due follow-ups.
3. Read the last file in `job-search/scans/` and note its date.
4. Give a plan for today, at most 4 items, in this order: interviews and offers (time sensitive), due follow-ups (`follow-up`), top unreviewed picks (`check-fit`), a new scan if the last one is over 7 days old (`find-jobs`).
5. **Funnel, once there is one.** When the tracker has 15 or more `applied` rows, group them by level (entry, experienced, lead or supervisor, manager and up, read from the title) and by target versus step-up title, and show each group's rate to an interview (`interviewing`, `offer`, `accepted`). If one group converts at least twice as often, say so in one line and suggest weighting the search toward it. Under 15, skip this; there is not enough to read.
6. Coach honestly. If they have reviewed many but applied to few, or applied to many with no replies after 3 weeks, say what that usually means (targeting, resume, or volume) and suggest the single change most likely to help. If the search is going fine, say so; do not invent problems. Search is slow and discouraging; one sentence of plain encouragement is fine, no cheerleading.
