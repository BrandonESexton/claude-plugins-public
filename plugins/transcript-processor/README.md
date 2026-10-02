# transcript-processor

Paste a meeting transcript (or name a recurring meeting) and it lands in the right place in a Markdown team-management workspace: the 1:1 file, the team meeting log, or a stakeholder playbook, with a summary, an action-items table, and observations.

## Use

- Paste a transcript, or "here's my 1:1 with Alex".
- "Process today's platform standup" (fetches it if a transcript fetcher and calendar lookup are configured).

## Setup

Copy `config.example.yaml` to `~/.config/transcript-processor/config.yaml`: your name, workspace folder, teams and their members' files, stakeholders, and any working-agreement rules to flag. If you skip it, the first run asks.

## Design notes

- **Routes on meeting titles, not IDs.** Video platforms often give each occurrence of a recurring meeting a new ID. Titles stay stable.
- **Looks across people.** The same struggle in two people's 1:1s is a team risk, so it goes in the team file instead of being buried in individual notes.
- **Your list, not a delegation tracker.** Only your own action items go to your task app; everyone else's stay in the notes.
- **Cleans up after itself.** Fetched transcripts are deleted once the notes hold the content.
- **Asks instead of guessing** when a meeting cannot be identified, and never fills in content that is not in the transcript.
