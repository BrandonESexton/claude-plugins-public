---
name: follow-up
description: >
  Use when it is time to follow up on an application or after an interview. Triggers on: "/follow-up",
  "should I follow up", "write a thank you", "I have not heard back", or when status shows a follow-up
  due. Drafts a short note and updates the tracker. Never sends it.
---

Read `${CLAUDE_PLUGIN_ROOT}/RULES.md` and `job-search/career.md`. Run `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" due` if he has not named the job.

Pick the case:
- **After applying, no reply (about 7 days):** 3 to 4 sentences. Restate the role, one concrete reason he fits, ask if they need anything more. Suggest sending to a named recruiter or hiring manager if he can find one; otherwise the application contact. Do not guess email addresses.
- **After an interview:** thank-you within 24 hours. Name something specific from the conversation (ask him what; do not invent it), one line tying it to his fit, and the next step they gave.
- **After a long silence post-interview (about 7 to 10 days):** brief check-in asking about timeline.
- **Rejection:** short gracious reply asking to stay in touch; mark the row `rejected`. Tell him a rejection is usually about volume of applicants, not him, only if that is plausible here.

Draft in his voice (plain, no stock phrases, no em dashes, under 100 words). Show it and stop. He sends it. Then update the row: `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" update <id> --followup <date 7 days out> --sent` (it counts the follow-up; `due` stops listing the job after two). If the row already shows two sent, do not draft a third; say so and tell him to move on.
