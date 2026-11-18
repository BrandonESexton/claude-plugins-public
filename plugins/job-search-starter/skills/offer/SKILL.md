---
name: offer
description: >
  Use when the user has a job offer or is asked about pay expectations. Triggers on: "/offer", "I got an
  offer", "they asked my salary", "should I negotiate", "is this offer good". Evaluates the offer against
  his floor, target, benefits, and the market, and drafts a negotiation script. Never replies for him.
---

Read `${CLAUDE_PLUGIN_ROOT}/RULES.md`, then `job-search/preferences.md` and `career.md`. Ask him to paste the offer (pay, pay type, hours, benefits, start date, anything in writing) and whether it is verbal or written.

## Evaluate

1. **Compare to his numbers.** Offer vs floor and target, in the same unit (convert hourly to annual with his actual hours, say the assumption). Below floor: say plainly that it does not meet what he told you he needs.
2. **Total value.** Add what is real: health premiums he would pay, retirement match, paid time off, bonus or overtime (marked as not guaranteed), tuition, schedule, commute cost. Compare against his must-have benefits.
3. **Market check.** Search public postings and salary pages for the same title and region. Give a range with sources, and say it is an estimate. Check the offer's position in it.
4. **Weak spots to ask about:** anything vague (bonus terms, probation, at-will clauses, non-compete, on-call or overtime expectations, benefit start date, relocation).
5. **Verdict:** Accept as is, Negotiate, or Decline, with the reasons. Lead with the weakest part of the offer.

## Negotiate (if he wants)

- Say that most employers expect it and a polite ask rarely loses an offer, but do not promise an outcome.
- Pick one or two asks ranked by what matters to him (base pay, a sign-on payment, start date, schedule, review in 6 months with written criteria). Anchor to his target or the market range, backed by two proof points from career.md.
- Draft a short script for a call and a short email, in his voice, no stock phrases, no em dashes. Include what to say if they say no (ask what is flexible, ask for the review in writing).
- Get the final terms in writing before he gives notice anywhere. Remind him not to resign from a current job until that is done.

Record it: `<python> "${CLAUDE_PLUGIN_ROOT}/scripts/tracker.py" update <id> --status offer --notes "<terms>"`, later `accepted` or `withdrawn`. Do not send anything for him.
