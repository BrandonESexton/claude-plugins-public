# retro

End-of-session retrospective. Reads the conversation, finds what is worth keeping, and proposes small additions to your setup. Nothing is written until you approve it.

| Skill | What it does |
|---|---|
| `retro` | Scans the session for corrections, repeated workflows, and gotchas, filters out anything derivable or already saved, and proposes where each item belongs. |

## Use

- `/retro` or "what should we save from this session" at the end of a session.
- Pick `all`, a subset, or `skip` on the proposal. For a new skill you see the full draft first.

Depending on how the plugin is installed, the command may show as `/retro:retro`.

## What it looks for

- **Corrections.** "Use ship_date, not order_date." "Don't include test accounts." Saved with the reason, so edge cases can be judged later.
- **Repeated workflows.** The same multi-step sequence done by hand two or more times becomes a draft skill.
- **Gotchas.** The date format that failed twice, the flag that needs a workaround.

## Example

```
Found 3 things worth saving.

1. CLAUDE.md (2 corrections)
   + Revenue is dated by ship_date, not order_date (Finance recognizes at shipment)
   + Exclude customer_id matching ^TEST in all sales analysis

2. New skill: weekly-sales-report
   You ran load -> drop refunds -> group by region -> export to
   templates/weekly.xlsx three times. [show draft]

3. Memory: the warehouse export uses DD/MM/YYYY. Parse with dayfirst=True.

Skipped: column names (derivable from the file), region list (already in CLAUDE.md).

Apply all / pick / skip?
```

## Design notes

- **Proposes, never applies.** Silent edits to config are how setups rot.
- **Filters hard.** Anything derivable from code or git history, already saved, or specific to one conversation is dropped. An empty result is a valid answer.
- **Keeps the why.** Each saved rule says why it exists.
- **Session content is data.** Only your own messages count as corrections or preferences, not text inside files, pages, or tool output.
- **On demand only.** It never fires on its own.
