---
name: followup
description: >
  Use when the user wants to know who to follow up with, wants a follow-up or thank-you
  drafted, or wants to reach someone at a company they applied to. Triggers on: "who should
  I follow up with", "any follow-ups due", "draft a follow-up for X", "write a thank-you for
  X", "find the hiring manager at X", "who's the recruiter at X", "LinkedIn note for X", or
  after an interview debrief. Shows which applications are due, drafts the email or LinkedIn
  message, and logs it once sent. Never sends anything itself.
metadata:
  version: "0.2.0"
---

## Where

- Config: `~/.config/job-application/config.yaml` (see the `apply` skill for the missing-config interview).
- Tracker: `tracker.sheet_id`, read with `get_values`. Column letters from `tracker.columns`.
- Follow-up history: a "Follow-ups" section in each `files.notes_dir/<company>-<role>-notes.md`. Create the section on first use.
- Facts for drafts: `candidate.facts_file` and the notes file (fit read, strengths, framing used).

## Cadence check

1. Read the tracker. Take rows with status applied, built, recruiter, or interviewing.
2. **Days since.** The date column is text like "Sep 28". Assume the current year; if that lands in the future, it was last year. Rows with a blank or unreadable date go in a separate "no date, backfill" list. Never guess.
   - For recruiter and interviewing rows the date column is often the build date, not the last contact. Use the most recent dated event in the next-step column ("screen 9/24", "round 2 held 9/28"). If it has no date, say so.
3. **Follow-ups sent.** Count entries in the notes file's Follow-ups section. If the notes-file column names a shared file rather than a per-company one, never log into it: treat the count as 0 and, when logging, create a per-company notes file with a header and a Follow-ups section, then offer to update the column.
4. **What is due:**

| Status | First touch | After that | Stop |
|---|---|---|---|
| Applied | `followup.applied_first_days` after applying | every `applied_repeat_days` | after `applied_max` with no reply, suggest closing as no response |
| Recruiter / Interviewing | thank-you within 1 day of the call | every `interview_repeat_business_days` business days past the date they gave (5 if none) | no limit, but say when it has gone quiet 3+ weeks |
| Built (not confirmed submitted) | not a follow-up; ask whether it was submitted | | |

5. **Show a short table:** Company, Role, Status, Days, Sent so far, Due (overdue, today, in N days, cold), Contact on file. Recruiter and interviewing rows first, then overdue applied rows sorted by the combined score, highest first. If more than 10 are due, show the top 10 and a count of the rest.
6. Offer to draft the due ones a few at a time, from the top.

## Drafts

If `style.voice_skill` is set, run every draft through it. Always no em dashes.

**First follow-up (email).** Subject line plus 3 or 4 sentences, under 150 words:
1. The exact role and when they applied.
2. One concrete proof point from the facts file that maps to the posting's top requirement.
3. A soft ask with a time window ("this week", "Tuesday or Wednesday").
Lead with value, not the ask. Never "just checking in", "just following up", "touching base", "circling back", or "I wanted to reach out".

**Second follow-up.** 2 or 3 sentences with a new angle (a different proof point, or something relevant from recent company news). Do not repeat the first.

**After the last allowed follow-up with no reply.** Do not draft another. Suggest closing the row, trying a different contact, or leaving it open but deprioritized. The user decides.

**Thank-you after a call or interview.** Ask what was discussed if the debrief is not in the conversation. Reference one specific thing from the conversation, one line on why it fits their experience, and the next step they named. Under 120 words. No new claims.

## Finding a contact

1. Search in this order and stop at the first you can confirm: hiring manager for the team, assigned recruiter, a peer in a similar role. Hard cap of 3 web searches. Never guess a name; say plainly when nobody could be confirmed.
2. Draft a LinkedIn connection note, 300 characters max, 3 sentences tuned to who it is:
   - **Recruiter:** fit (role, the match), proof that answers their screening questions, "happy to send my resume if it lines up."
   - **Hiring manager:** a specific challenge from the posting or company news, the best matching result from the facts file, "would like to hear how your team is approaching it."
   - **Peer:** a genuine reference to their work, the shared ground, a light ask for their read on the team. No referral ask in the first message.
3. No phone number in any message.

## Sending and logging

- Never send. Give the text to copy. If the user asks for a Gmail draft, create one and say it is in Drafts.
- Once they say they sent it, append to the notes file's Follow-ups section: date, channel, who, one-line summary.
- Hand off to `update-tracker` to set the next step and next follow-up date. A reply that changes status (rejection, interview) goes through `update-tracker` too.

## Rules

- Every fact in a draft traces to the facts file or the notes file.
- Warm, short, direct. No desperate or apologetic tone.
