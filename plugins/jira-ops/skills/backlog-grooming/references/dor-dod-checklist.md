# Definition of Ready / Definition of Done

## Description template

Every groomed ticket's description is rewritten to exactly this shape.

**Earlier grooming:** if the description already contains a grooming pass (a `**1. Description**` / `**2. Definition of Ready**` header), keep only the reporter's original text that precedes it as the verbatim original. Discard the old scaffold instead of nesting it.

```
**Original Description:**
<verbatim original, preserved in case grooming misreads intent>
---
**1. Description**
Who: (the requester or stakeholder this is for; default to the reporter or the team they
     name. Not the engineer who will do the work.)
What: ...
Why: ...

**2. Definition of Ready**
✅/☐ Problem or goal stated (who/what/why)
✅/☐ Acceptance criteria specific and testable
✅/☐ Sized to fit one story
✅/☐ Story points assignable
✅/☐/N/A Linked to Epic (if applicable)
✅/☐ Dependencies identified
✅/☐ No open content questions
[MISSING (needs reporter input): <specific ask>]
(Group failing items by root cause into as few direct questions as needed. If seven items
fail because the ticket has no clear ask at all, that is one or two questions, not seven.
Only present when a gap exists.)

**3. Definition of Done**
☐/N/A Acceptance criteria met
☐/N/A Code reviewed and merged
☐/N/A Tested
☐/N/A Demoed to stakeholder
☐/N/A Architecture sign-off
☐/N/A Documentation updated
(N/A with a short reason only when it is not obvious why)

**4. Dependencies**
- <ticket key + one-line relationship, or "None identified">
```

## The 7 readiness items

1. **Problem or goal stated**: real who/what/why, not just a title.
2. **Acceptance criteria specific and testable**: not "works correctly".
3. **Sized to fit one story**: not epic or org-wide breadth.
4. **Story points assignable**: concrete enough to size within the configured maximum.
5. **Linked to Epic**: N/A for Sub-task and Spike. For other types this is always ✅ by the time readiness is judged, because the skill assigns a best-guess epic itself (falling back to the catch-all). A missing epic is never a reporter question.
6. **Dependencies identified**: related tickets, teams, or systems named, not implied.
7. **No open content question**: nothing blocking that only the reporter can answer.

**Verdict:** every applicable item ✅ means Ready. Any ☐ means Not Ready.

## Definition of Done: scaffold only

Written at grooming time as ☐ or N/A, never evaluated to ✅ here. N/A when the item does not apply to this kind of work (no code to review, no visible output to demo, no architecture touched, no doc surface).

## Rendering rule

Never use markdown `- [ ]` checkboxes in a Jira description or comment. Jira's markdown converter drops them silently. Use ✅, ☐, and N/A as plain text.

## Comment templates

Every template ends with the configured `grooming.signature`, shown here as `<signature>`.

### Not ready (to the reporter)

```
Hi [reporter], this one needs a bit more before it's ready for sprint planning. Could you
clarify:
1. <gap 1, as a direct question>
2. <gap 2, as a direct question>

<signature>
```

### Duplicate (posted on both tickets)

```
This looks like a likely duplicate of [OTHER-KEY]: <one-line reason>. Flagging for triage.
Let me know if these should be merged or kept separate.

<signature>
```

### AI spend increase: missing info

Ask only for what is actually missing.

```
Hi [reporter], before this can move forward I need a couple of things:
1. Can you set your manager as the Approving Manager on this ticket?
2. Can you paste two prompts you use regularly so we can run them through an efficiency
   review?

<signature>
```
