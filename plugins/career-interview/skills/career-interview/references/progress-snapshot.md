# Progress Snapshot

Emit every ~10 counted questions and whenever the user says "pause". Tell the user: "Paste this into a new chat to pick up where we left off." Keep it compact; it is the only memory in environments without a filesystem. In a filesystem environment, also write it to `career.draft.md`.

```
CAREER-INTERVIEW SNAPSHOT v1
Date: YYYY-MM-DD
Question: 23 of ~45
Phase: 2 (role deep dives), current role: <Title, Company>
Resume baseline: <name, roles with dates in one line each>
Targets: <roles, level, industries, mode, comp, constraints>
Gap map: <open gaps still to cover>
Captured so far:
- <Role>: scope; accomplishment + metric (~estimate marks); left-off items
- Skills: <skill> (level): proof
- Stories drafted: <titles>
- Claim boundaries: <items>
Open items: <numbers still needed>
Next: <the next question topic>
```

Resume rule: when the user pastes a snapshot, confirm it in two lines, do not repeat answered questions, and continue the counter from the saved number. If the resume file is not attached again, ask for it only if a gap needs rechecking.
