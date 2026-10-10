---
name: adr-studio
description: "Guides an architecture decision from question to a defensible, reviewed Architecture Decision Record (ADR). Interviews for context and constraints, builds weighted criteria, scores options with a deterministic script that includes sensitivity analysis, drafts the ADR with a Mermaid diagram, then runs an adversarial pre-mortem. Use when the person asks to write an ADR, compare architecture options, justify a technology choice, decide between vendors or patterns, or invokes /adr-studio."
---

# ADR Studio

Turns "should we use X or Y?" into a decision record someone can audit a year later. The value is the reasoning trail, not the document: every score has a stated rationale, the winner is stress-tested, and the strongest counter-argument is written down.

## Workflow

### 1. Frame the decision (interview, max 5 questions, one at a time)
Ask only what you cannot infer from the repo or conversation:
1. What decision is being made, and by when?
2. What forces it now (new requirement, cost, risk, end of support)?
3. Hard constraints (compliance, existing platform, budget ceiling, team skills)?
4. Who is affected and who must approve?
5. What are the candidate options? Always add "do nothing / defer" as an explicit option.

If the repo has existing ADRs (`docs/adr/`, `adr/`, `docs/decisions/`), read them first, match numbering and format, and link related ones.

### 2. Build criteria and weights
Propose 5 to 8 criteria from `references/criteria-catalog.md`, trimmed to what matters here. Ask the person to confirm or adjust weights (1-10). Do not silently accept defaults: weights are the most contestable part of any decision.

### 3. Score options
For each option and criterion, assign a 1-5 score **with a one-line rationale grounded in a fact** (a doc, a number, a constraint). No rationale, no score. Mark any score based on assumption rather than evidence with `assumed: true`. Write the input JSON (schema in `references/scoring-schema.md`) to the scratchpad or `docs/adr/`.

### 4. Run the math
```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/adr-studio/scripts/score_matrix.py input.json
```
It prints the ranked table and a **sensitivity analysis**: how much any single weight must move to change the winner, and the share of 1,000 random weight perturbations (+/-30%) in which each option wins. Report both. If the winner is fragile (wins < 70% of perturbations) or the margin is under 5%, say so plainly and name the weight that flips it.

### 5. Draft the ADR
Use `references/adr-template.md`. Requirements:
- Status starts as `Proposed`.
- Context states forces, not solutions.
- Include the scored matrix and the sensitivity result.
- Include a Mermaid diagram of the chosen design (context or sequence, whichever clarifies most).
- Consequences list both positive and negative. At least one real negative.
- A "Revisit when" section with measurable triggers.

### 6. Pre-mortem
Invoke the `adr-challenger` agent with the draft. Incorporate its top 3 risks into Consequences, or record why you rejected each. Do not skip this step even if the decision looks obvious.

### 7. Save and index
Write to `docs/adr/NNNN-kebab-title.md` (next free number). Update `docs/adr/README.md` index if it exists. Never mark `Accepted` yourself: that is the approvers' call.

## Rules
- No fabricated facts. If you do not know a price, limit, or SLA, mark it `assumed` or look it up.
- No em dashes in output.
- Keep the ADR under two pages. Link out for detail.
- A decision with one option is not a decision: refuse and ask for alternatives.
