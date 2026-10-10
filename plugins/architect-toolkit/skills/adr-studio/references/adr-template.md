# ADR-NNNN: <Decision as a short noun phrase>

- **Status:** Proposed
- **Date:** YYYY-MM-DD
- **Deciders:** <names/roles>
- **Related:** <ADR links>

## Context
Forces driving the decision: requirement, constraint, deadline. No solutions here.

## Options considered
1. **<Option A>** one-line description
2. **<Option B>**
3. **Do nothing / defer** what happens if we wait

## Evaluation
Weighted scoring (1-5, weights 1-10). Rationale for each score is in `<input.json>`.

| Option | Weighted score | % of max | Assumed inputs |
|---|---|---|---|

**Sensitivity:** <winner> wins in N% of 1,000 weight perturbations (+/-30%). Weight most likely to flip the result: <criterion> (change of X).

## Decision
We will <do X> because <two or three decisive reasons tied to the top-weighted criteria>.

## Design
```mermaid
flowchart LR
  A[Client] --> B[Service]
```

## Consequences
**Positive**
- ...

**Negative / accepted risks**
- ...

**Pre-mortem findings**
| Risk | Likelihood | Impact | Mitigation or reason accepted |
|---|---|---|---|

## Revisit when
- Measurable trigger 1 (e.g. monthly cost exceeds $X, p99 latency above Y ms)
- Trigger 2
