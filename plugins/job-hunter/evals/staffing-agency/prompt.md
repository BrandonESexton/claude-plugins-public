---
description: Hidden end employer behind a staffing agency. The review must say so and not guess the employer.
tags: [smoke, review]
runs: 2
max_turns: 30
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
append_system_prompt: "Test environment. The job-search/ folder next to this case is the user's files (career.md, preferences.md). Web search, the browser, and the tracker script may be unavailable: say so in one line where a step needs them and carry on with the review. Ask your closing questions as plain text."
---

Is this a good fit for me?

Journeyman Electrician (Pittsburgh area)
Posted by Keystone Trade Staffing

Our client, a large commercial contractor in the Pittsburgh area, is hiring journeyman electricians for a 6-month contract-to-hire. Commercial retrofits and panel work.
- Pennsylvania journeyman license
- 3+ years commercial experience
Pay: $36 per hour, W2 through Keystone. Benefits after 90 days.
