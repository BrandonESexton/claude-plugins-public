# Prompt efficiency review: AI spend increase requests

Runs once a request clears the two-item bar (approving manager set, real usage evidence), and must post before the ticket moves to To Do. The point is not to gatekeep. It is to make the extra budget go further, and to give the requester something useful back for asking.

## What can be judged from a static sample

There is no chat history and no interview, usually just two pasted prompts or one skill file. Comment only on what the sample shows:

- **What is pasted in or attached**: a big block that is not needed, or material re-explained that did not need to be.
- **Asking clearly the first time**: vague scope, missing format or constraints that will force a retry.
- **How much is asked to be written or redone**: a full regeneration where a targeted edit would do, or an open-ended long-output request.
- **Model and feature choice, connected data pulls**: only if the prompt names a model or describes a broad tool sweep. Otherwise there is no signal; say so.
- **Long chats vs fresh starts**: almost never visible from one prompt. Skip unless the prompt drags a whole prior thread forward.

If a prompt is already efficient, say so. Do not manufacture a critique.

## Per prompt

Name what makes it expensive (unneeded context, broad or repeated tool calls, vague scope, long output, redundant back-and-forth), rewrite it as a leaner version that produces a comparable result, and explain the key change in one sentence.

## Skill-file variant

Same lens, applied to the skill's instructions: does it load large reference content every time instead of on demand, repeat instructions, ask for full-document output where an edit would do, or fan out broad tool calls by default. A well-built skill gets told so.

## Optional hints (from config)

- `ai_spend.alternative_tool_hint`: when a prompt is bulk, low-reasoning text work, suggest the alternative for that one use case. Never a blanket "use something else".
- `ai_spend.team_check_hints`: when a prompt matches a listed topic, add the matching hint (for example, check with the team that already owns that system).

## Voice

Specific, encouraging, non-judgmental. Someone who wants the requester to get more out of the tool.

## Templates

### Review (posted on Ready tickets, before the move)

```
Hi [reporter], thanks for the examples. Here's a quick efficiency pass so this increase
goes further.

**Prompt 1**
What's costing tokens: <1-2 sentences, or "this one's already efficient, nice work">
A more efficient version: <rewrite, only if there's a real improvement>
Why: <1 sentence>

**Prompt 2**
What's costing tokens: ...
A more efficient version: ...
Why: ...

<0-2 sentences of habit notes, only if the samples support them>
<optional alternative-tool or team-check hint>

<signature>
```

### Missing info: skill named but not provided

```
Hi [reporter], you mentioned using a skill rather than raw prompts. Could you attach the
skill file (or paste its full content in a comment) so we can run the same efficiency
review on it?

<signature>
```
